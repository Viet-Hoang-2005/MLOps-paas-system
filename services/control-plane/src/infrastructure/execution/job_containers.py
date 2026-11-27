"""Recoverable training/drift runtimes, with ownership checked before I/O."""

import docker.errors
from django.db import transaction
from django.utils import timezone

from common.api.exceptions import Conflict
from common.logging_utils import sanitize

from .docker_runtime import create_or_attach_container, get_owned_container, remove_owned_container


def project_for(resource, kind):
    return resource.project if kind == "training" else resource.monitor.version.project


def labels_for(resource, kind):
    project = project_for(resource, kind)
    return {
        "mlops_tenant_id": str(resource.owner.tenant_id) if kind == "training" else str(project.owner.tenant_id),
        "mlops_project_id": resource.runtime_project_id if kind == "training" else str(project.public_id),
        f"mlops_{kind}_id": str(resource.public_id),
    }


def identity_field(kind):
    return "external_job_id" if kind == "training" else "external_run_id"


def owned(client, resource, kind):
    return get_owned_container(
        client,
        f"{kind}-{resource.public_id}",
        labels_for(resource, kind),
        getattr(resource, identity_field(kind)),
        error_cls=Conflict,
        ownership_msg="Runtime ownership does not match this execution.",
        identity_msg="Runtime identity changed for this execution.",
    )


def start(docker_client, resource, kind, **kwargs):
    project = project_for(resource, kind)
    with transaction.atomic():
        locked_project = type(project).objects.select_for_update().get(pk=project.pk) if project else None
        current = type(resource).objects.select_for_update().get(pk=resource.pk)
        lease = resource.execution_check_token
        if lease and (
            current.execution_check_token != lease
            or not current.execution_check_lease_until
            or current.execution_check_lease_until <= timezone.now()
        ):
            raise Conflict("Execution lease expired before dispatch.")
        if (
            (locked_project and locked_project.deletion_state != "active")
            or current.execution_stop_requested
            or current.status in {"cancelled", "cancelling", "failed", "completed"}
        ):
            raise Conflict("Execution is no longer active.")
    container = create_or_attach_container(
        docker_client,
        f"{kind}-{resource.public_id}",
        labels_for(resource, kind),
        getattr(resource, identity_field(kind)),
        error_cls=Conflict,
        ownership_msg="Runtime ownership does not match this execution.",
        identity_msg="Runtime identity changed for this execution.",
        missing_msg="Recorded runtime is missing; create a new attempt.",
        **{**kwargs, "name": f"{kind}-{resource.public_id}"},
    )
    field = identity_field(kind)
    rows = type(resource).objects.filter(pk=resource.pk)
    if lease:
        rows = rows.filter(execution_check_token=lease, execution_check_lease_until__gt=timezone.now())
    rows.update(**{field: container.id})
    setattr(resource, field, container.id)
    current = type(resource).objects.filter(pk=resource.pk).first()
    if not current or current.execution_stop_requested or current.status in {"cancelled", "failed", "completed"}:
        remove(docker_client.client, resource, kind)
    return container


def observe(client, resource, kind):
    try:
        container = owned(client, resource, kind)
        state = container.attrs.get("State", {})
        started = state.get("StartedAt")
        result = {"runtime_id": container.id}
        if started and not started.startswith("0001-"):
            result["started_at"] = started
        if state.get("Status") == "created":
            return {**result, "status": "created"}
        if state.get("Status") in {"running", "restarting", "paused"}:
            return {**result, "status": "running"}
        finished = state.get("FinishedAt")
        if finished and not finished.startswith("0001-"):
            result["finished_at"] = finished
        logs = sanitize(
            container.logs(stdout=True, stderr=True, tail=200).decode("utf-8", errors="replace"), limit=None
        )[-12000:]
        code = state.get("ExitCode", 1)
        return {
            **result,
            "status": "completed" if code == 0 else "failed",
            "exit_code": code,
            "logs": logs,
            "error": logs[-12000:] or "Runtime exited unsuccessfully." if code else "",
        }
    except docker.errors.NotFound:
        return {"status": "not_found"}
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__}


def remove(client, resource, kind):
    def _get():
        container = owned(client, resource, kind)
        return container

    remove_owned_container(_get, stop_timeout=30)
    return {"confirmed": True}
