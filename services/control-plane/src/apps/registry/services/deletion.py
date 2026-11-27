import logging

import docker.errors
from django.db import transaction
from django.db.models import Q

from apps.catalog.models import ModelProject, PreviewAsset
from apps.deployment.models import Build, BuildInputAsset, Deployment
from apps.deployment.services.cache import invalidate_model_server_cache
from apps.drift.models import DriftMonitor, DriftRun
from apps.drift.services.deletion import cleanup_drift_monitor
from apps.registry.models import ModelArtifact, ModelVersion, RegistryAlias
from common.api.exceptions import Conflict, ServiceUnavailable
from common.logging import record_transition
from common.redis_client import redis_client
from infrastructure.docker import DockerClient
from infrastructure.execution import deployment_backend
from infrastructure.harbor import HarborClient
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import version_prefix

logger = logging.getLogger(__name__)


def _check_ct_references(project, version):
    from apps.ct.models import EvaluationGate, EvidenceWindow, MaintenanceDecision, MaintenanceRun

    # Stored lineage still protects versions when continuous training is disabled.
    if (
        MaintenanceRun.objects.filter(project=project, state__in=MaintenanceRun.ACTIVE_STATES)
        .filter(Q(expected_champion=version) | Q(candidate=version))
        .exists()
    ):
        raise Conflict("This model version is referenced by an active continuous training run.")
    if (
        EvaluationGate.objects.filter(Q(candidate=version) | Q(champion=version)).exists()
        or EvidenceWindow.objects.filter(champion=version).exists()
        or MaintenanceDecision.objects.filter(expected_champion=version).exists()
        or MaintenanceRun.objects.filter(Q(expected_champion=version) | Q(candidate=version)).exists()
    ):
        raise Conflict("This model version is referenced by continuous training lineage records.")


def _remove_build_image(build):
    if not build.image_uri:
        return
    if build.backend == "argo":
        HarborClient().delete_artifact(build.image_uri)
        return
    try:
        DockerClient().client.images.remove(build.image_uri, force=True, noprune=False)
    except docker.errors.NotFound:
        pass


def delete_model_version(version: ModelVersion, *, storage=None, image_remover=None) -> None:
    """Delete a ModelVersion along with its runtime pods, monitors, S3 artifacts, and image."""
    image_remover = image_remover or _remove_build_image

    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=version.project_id)
        locked = (
            ModelVersion.objects.select_for_update(of=("self",))
            .select_related("project__owner")
            .filter(pk=version.pk)
            .first()
        )
        if locked is None:
            return
        if project.deletion_state != "active":
            raise Conflict("This project is already being deleted.")
        _check_ct_references(project, locked)

        deployments = list(locked.deployments.select_related("endpoint").all())
        if any(item.status in {"deploying", "unconfirmed"} for item in deployments):
            raise Conflict("Stop the deployment in progress before deleting this version.")
        locked.deletion_requested = True
        locked.save(update_fields=["deletion_requested"])
        DriftRun.objects.filter(monitor__version=locked).update(execution_stop_requested=True)
        deployment_pks = {item.pk for item in deployments}
        if project.active_deployment_id in deployment_pks:
            project.active_deployment = None
            project.save(update_fields=["active_deployment", "updated_at"])

        monitors = list(locked.drift_monitors.all())
        builds = list(locked.builds.all())
        artifact_uris = list(locked.artifacts.values_list("uri", flat=True))
        artifact_pks = list(locked.artifacts.values_list("pk", flat=True))
        s3_prefix = version_prefix(project.owner.tenant_id, project.public_id, locked.public_id).rstrip("/") + "/"
        version_public_id = locked.public_id

    storage = storage or S3Storage()
    invalidate_model_server_cache(str(version_public_id))

    for deployment in deployments:
        try:
            result = deployment_backend(deployment.backend).stop(deployment)
        except Exception as exc:
            logger.warning("Failed to stop deployment %s during version cleanup", deployment.public_id, exc_info=True)
            raise ServiceUnavailable("Could not stop the deployment. Retry deletion.") from exc
        if deployment.backend == "argo" and (not isinstance(result, dict) or not result.get("confirmed")):
            raise ServiceUnavailable("The deployment stop has not been confirmed. Retry deletion after it stops.")
        try:
            redis_client().delete(f"deployment_logs:{deployment.public_id}")
        except Exception:
            logger.warning("Failed to delete Redis logs for deployment %s", deployment.public_id, exc_info=True)

    for monitor in monitors:
        cleanup_drift_monitor(monitor, storage=storage)

    build_pks = {build.pk for build in builds}
    seen_images = set()
    for build in builds:
        uri = build.image_uri
        if not uri or uri in seen_images:
            continue
        seen_images.add(uri)
        if Build.objects.filter(project_id=version.project_id, image_uri=uri).exclude(pk__in=build_pks).exists():
            continue
        try:
            image_remover(build)
        except Exception as exc:
            logger.warning("Failed to remove image %s for version %s", uri, version_public_id, exc_info=True)
            raise ServiceUnavailable("Could not delete the version image. Retry deletion.") from exc

    shared_uris = set()
    for uri in artifact_uris:
        if not uri or not uri.startswith(f"s3://{storage.bucket}/"):
            continue
        shared = (
            ModelArtifact.objects.exclude(pk__in=artifact_pks).filter(uri=uri).exists()
            or BuildInputAsset.objects.filter(s3_uri=uri).exists()
            or PreviewAsset.objects.filter(s3_uri=uri).exists()
            or DriftMonitor.objects.exclude(version=version).filter(reference_uri=uri).exists()
        )
        if shared:
            shared_uris.add(uri)

    if not shared_uris:
        try:
            storage.delete_prefix(s3_prefix)
        except Exception as exc:
            logger.warning("Failed to delete S3 version prefix %s", s3_prefix, exc_info=True)
            raise ServiceUnavailable("Could not delete the version files. Retry deletion.") from exc

    for uri in artifact_uris:
        if not uri or not uri.startswith(f"s3://{storage.bucket}/") or uri in shared_uris:
            continue
        try:
            storage.delete(uri)
        except Exception as exc:
            logger.warning("Failed to delete version artifact %s", uri, exc_info=True)
            raise ServiceUnavailable("Could not delete the version files. Retry deletion.") from exc

    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=version.project_id)
        locked = (
            ModelVersion.objects.select_for_update(of=("self",))
            .select_related("project__owner")
            .filter(pk=version.pk)
            .first()
        )
        if locked is None:
            return
        if project.deletion_state != "active":
            raise Conflict("This project is already being deleted.")
        _check_ct_references(project, locked)
        if project.active_deployment_id in {d.pk for d in locked.deployments.all()}:
            project.active_deployment = None
            project.save(update_fields=["active_deployment", "updated_at"])

        RegistryAlias.objects.filter(version=locked).delete()
        Deployment.objects.filter(version=locked).delete()
        Build.objects.filter(version=locked).update(
            version=None,
            registration_status="unregistered",
            registration_error="",
            image_uri="",
            image_digest="",
        )
        record_transition(locked, "deleted")
        locked.delete()
