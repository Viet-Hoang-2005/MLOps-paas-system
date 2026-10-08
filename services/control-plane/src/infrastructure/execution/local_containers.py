"""Deterministic Docker attempts; never act on a client-supplied container ID."""

from datetime import timedelta

import docker.errors
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.catalog.models import ModelProject
from common.api.exceptions import Conflict
from infrastructure.docker import DockerClient


class ContainerOwnershipError(RuntimeError):
    pass


def identity(resource, kind):
    project = resource.project if kind == "build" else resource.version.project
    return {
        "mlops_tenant_id": str(project.owner.tenant_id),
        "mlops_project_id": str(project.public_id),
        f"mlops_{'build' if kind == 'build' else 'deployment'}_id": str(resource.public_id),
    }


def owned_container(client, resource, kind):
    container = client.containers.get(f"{kind}-{resource.public_id}")
    container.reload()
    labels = container.attrs.get("Config", {}).get("Labels") or {}
    has_mlops_labels = any(key.startswith("mlops_") for key in labels)
    if has_mlops_labels:
        if any(labels.get(key) != value for key, value in identity(resource, kind).items()):
            raise ContainerOwnershipError("Docker container ownership does not match this execution.")
    recorded = getattr(resource, "external_build_id" if kind == "build" else "external_deployment_id")
    if recorded and recorded != container.id:
        raise ContainerOwnershipError("Docker container identity changed for this execution.")
    return container


def start_container(docker_client, resource, kind, **kwargs):
    project = resource.project if kind == "build" else resource.version.project
    client = docker_client.client
    try:
        container = owned_container(client, resource, kind)
    except docker.errors.NotFound:
        recorded = getattr(resource, "external_build_id" if kind == "build" else "external_deployment_id")
        if recorded:
            raise RuntimeError("The recorded Docker execution is missing; create a new attempt.") from None
        kwargs["labels"] = {**kwargs.get("labels", {}), **identity(resource, kind)}
        try:
            container = docker_client.run(**kwargs)
        except docker.errors.APIError as exc:
            if exc.status_code != 409:
                raise
            # Another delivery created this same attempt while our lookup ran.
            container = owned_container(client, resource, kind)
    if container.attrs.get("State", {}).get("Status") == "created":
        container.start()
    container.reload()
    field = "external_build_id" if kind == "build" else "external_deployment_id"
    rejected = False
    with transaction.atomic():
        current_project = ModelProject.objects.select_for_update().filter(pk=project.pk).first()
        current = type(resource).objects.select_for_update().filter(pk=resource.pk).first()
        if (
            not current or not current_project or not current_project.is_active
            or current_project.deletion_state != "active"
            or getattr(current, "deletion_state", "active") != "active"
            or current.status in {"cancelled", "stopped"}
        ):
            rejected = True
        else:
            now = timezone.now()
            deadline = current.execution_deadline_at or now + timedelta(seconds=(
                settings.LOCAL_BUILD_TIMEOUT_SECONDS if kind == "build"
                else settings.LOCAL_DEPLOY_READINESS_TIMEOUT_SECONDS
            ))
            if kind == "deploy" and not current.external_deployment_id:
                created = parse_datetime(container.attrs.get("Created", ""))
                if created and timezone.is_aware(created):
                    deadline = created + timedelta(seconds=settings.LOCAL_DEPLOY_READINESS_TIMEOUT_SECONDS)
            type(resource).objects.filter(pk=current.pk).update(**{
                field: container.id, "execution_deadline_at": deadline,
                "next_execution_check_at": now,
            })
            setattr(resource, field, container.id)
            resource.execution_deadline_at = deadline
    if rejected:
        container.remove(force=True)
        raise Conflict("Execution was cancelled or its project is being deleted.")
    return container


def inspect_container(resource, kind, client=None):
    return owned_container(client or DockerClient(client=None, timeout=3).client, resource, kind)


def remove_container(resource, kind, client=None):
    try:
        inspect_container(resource, kind, client).remove(force=True)
    except docker.errors.NotFound:
        pass
