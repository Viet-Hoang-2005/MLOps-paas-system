import json
import logging
from datetime import timedelta

from botocore.exceptions import ClientError
from django.db import transaction
from django.utils import timezone
from requests import HTTPError

from apps.catalog.models import ModelProject
from apps.deployment.services.completion import complete_reported_build, expected_build_image, valid_build_result
from common.logging import record_transition
from infrastructure.execution import deployment_backend
from infrastructure.harbor import HarborClient
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_result_key

logger = logging.getLogger(__name__)


def _verified_build_result(build):
    storage = S3Storage()
    key = build_result_key(build.project.owner.tenant_id, build.project.public_id, build.public_id)
    try:
        result = json.loads(storage.read(f"s3://{storage.bucket}/{key}"))
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise
    image = expected_build_image(build)
    if (
        not isinstance(result, dict)
        or result.get("build_id") != str(build.public_id)
        or result.get("status") != "success"
        or not valid_build_result(build, result, image)
    ):
        raise ValueError("Invalid build result.")
    try:
        package_size = storage.head(build.package_uri).size_bytes
        digest = HarborClient().artifact_digest(image)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
            raise ValueError("Build package is missing.") from exc
        raise
    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise ValueError("Build image is missing.") from exc
        raise
    if not package_size or digest != result["image_digest"]:
        raise ValueError("Build package or image verification failed.")
    return result


def fail_unconfirmed_build(build, message):
    from apps.deployment.tasks import cleanup_failed_build_artifacts

    now = timezone.now()
    build.status = "failed"
    build.error_message = message
    build.completed_at = now
    build.next_execution_check_at = now
    build.execution_check_token = None
    build.execution_check_lease_until = None
    build.save(update_fields=[
        "status", "error_message", "completed_at", "next_execution_check_at", "updated_at",
        "execution_check_token", "execution_check_lease_until",
    ])
    record_transition(build, "failed", reason=message)
    transaction.on_commit(lambda: cleanup_failed_build_artifacts.delay(str(build.public_id), True), robust=True)


def apply_argo_observation(row, kind, token, observation, *, retain_lease=False, deadline_check=False):
    from apps.deployment.tasks import _mark_deployment_succeeded, mark_argo_deployment_failed
    from apps.notifications.hooks import notify_build_result, notify_deployment_result
    from apps.observability.services.executions import _valid, project_for

    project = project_for(row, kind)
    status = observation["status"]
    result = None
    healthy = False
    verification_available = True
    try:
        deadline_passed = row.execution_deadline_at and row.execution_deadline_at <= timezone.now()
        if kind == "build" and (status in {"completed", "failed", "not_found"} or deadline_passed):
            result = _verified_build_result(row)
        elif kind == "deployment" and status == "completed":
            healthy, _ = deployment_backend("argo").health(row)
    except ValueError:
        logger.warning("Invalid Argo %s result for %s.", kind, row.public_id)
    except Exception:
        verification_available = False
        logger.warning("Could not verify Argo %s result for %s.", kind, row.public_id, exc_info=True)

    with transaction.atomic():
        project = ModelProject.objects.select_for_update().filter(pk=project.pk).first()
        if not project:
            return "ignored"
        current = type(row).objects.select_for_update().filter(pk=row.pk).first()
        active = current and current.backend == "argo" and project.is_active and project.deletion_state == "active"
        if active and kind == "build":
            active = current.status == "building" and current.deletion_state == "active"
        elif active:
            active = current.status in {"deploying", "unconfirmed"} and not current.version.deletion_requested
        if not active or not _valid(current, token):
            return "ignored"

        completed = False
        if kind == "build" and result and current.package_uri == row.package_uri:
            current = complete_reported_build(current, result, expected_build_image(current))
            record_transition(current, current.status, source="argo-observation")
            transaction.on_commit(lambda: notify_build_result(current), robust=True)
            completed = True
        elif kind == "build" and not result and verification_available and (deadline_check or status == "failed"):
            message = (
                "Build execution exceeded its deadline."
                if deadline_check
                else "Argo build workflow failed. See execution logs."
            )
            fail_unconfirmed_build(current, message)
            transaction.on_commit(lambda: notify_build_result(current), robust=True)
            return current.status
        elif kind == "deployment" and (healthy or status == "failed"):
            workflow = f"deploy-{current.public_id}"
            if current.external_deployment_id and current.external_deployment_id != workflow:
                return "ignored"
            current.external_deployment_id = workflow
            current.save(update_fields=["external_deployment_id", "updated_at"])
            if healthy:
                completed = _mark_deployment_succeeded(current)
            else:
                mark_argo_deployment_failed(current, f"Deployment workflow {workflow} failed. See execution logs.")
                completed = True
            current.refresh_from_db()
            if completed:
                transaction.on_commit(lambda: notify_deployment_result(current), robust=True)

        if retain_lease and not completed:
            return None
        current.execution_check_token = None
        current.execution_check_lease_until = None
        retry_seconds = 30
        if kind == "build" and not current.callback_wait_until:
            retry_seconds = 60
        elif kind == "deployment" and current.status == "unconfirmed":
            retry_seconds = 120
        current.next_execution_check_at = None if completed else timezone.now() + timedelta(seconds=retry_seconds)
        current.save(update_fields=["execution_check_token", "execution_check_lease_until", "next_execution_check_at"])
        return current.status
