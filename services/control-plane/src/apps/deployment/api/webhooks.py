import re

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services.cache import invalidate_model_server_cache
from apps.deployment.services.callbacks import valid_callback_token
from apps.deployment.services.logs import append_deployment_log
from apps.deployment.tasks import _mark_deployment_healthy, cleanup_failed_build_artifacts
from apps.observability.services.outbox import enqueue_event
from apps.registry.services.versions import register_successful_build
from common.api.permissions import HasInternalWebhookSecret
from common.logging import record_transition
from infrastructure.execution.image_references import temporary_image_reference


def _dict_payload(value):
    return value if isinstance(value, dict) else {}


class HasDeploymentCallbackToken(BasePermission):
    message = "Invalid deployment reporter token."

    def has_permission(self, request, view):
        return valid_callback_token(
            request.headers.get("X-Deployment-Callback-Token", ""), view.kwargs["deployment_id"]
        )


class DeploymentWebhookEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (HasDeploymentCallbackToken,)

    def post(self, request, deployment_id):
        payload = _dict_payload(request.data)
        incoming = str(payload.get("status", "")).lower()
        workflow = str(payload.get("workflow_name", ""))
        if incoming not in {"succeeded", "failed", "error"} or not re.fullmatch(
            r"deploy-model-job-[a-z0-9-]{1,100}", workflow
        ):
            return Response({"detail": "A terminal workflow result and workflow name are required."}, status=400)
        with transaction.atomic():
            deployment = get_object_or_404(
                Deployment.objects.select_for_update().select_related("version__project"),
                public_id=deployment_id,
            )
            if deployment.backend != "argo":
                return Response({"detail": "This deployment does not use Argo."}, status=409)
            if deployment.status in {"healthy", "failed", "stopped"}:
                return Response({"status": deployment.status, "duplicate": True})
            if deployment.version.project.deletion_state != "active":
                return Response({"status": deployment.status, "ignored": True})
            if deployment.external_deployment_id and deployment.external_deployment_id != workflow:
                return Response({"detail": "Workflow does not match this deployment."}, status=409)
            deployment.external_deployment_id = workflow
            deployment.save(update_fields=["external_deployment_id", "updated_at"])
            if incoming == "succeeded":
                _mark_deployment_healthy(deployment)
                result = "healthy"
            else:
                result = "failed"
                deployment.status = result
                deployment.error_message = (
                    f"Deployment workflow {workflow} finished with {incoming}. See execution logs."
                )
                deployment.save(update_fields=["status", "error_message", "updated_at"])
                Endpoint.objects.filter(deployment=deployment).update(
                    health_status="unhealthy", last_checked_at=timezone.now()
                )
                invalidate_model_server_cache(str(deployment.version.public_id))
                append_deployment_log(deployment, deployment.error_message)
                record_transition(deployment, result, source="webhook", reason="Deployment workflow failed")
                enqueue_event(
                    topic="deployment.events",
                    aggregate_type="deployment",
                    aggregate_id=deployment.public_id,
                    event_type="deployment.changed",
                    payload={"deployment_id": str(deployment.public_id), "status": result},
                )
        return Response({"status": result})


class BuildWebhookEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (HasInternalWebhookSecret,)

    def post(self, request, build_id):
        build = Build.objects.select_related("project", "project__owner", "version").get(public_id=build_id)
        incoming = str(request.data.get("status", "")).lower()
        if build.status in {"ready", "failed", "cancelled"}:
            return Response(
                {
                    "status": build.status,
                    "version_id": str(build.version.public_id) if build.version_id else None,
                    "duplicate": True,
                }
            )
        if incoming in {"success", "succeeded", "ready", "completed"}:
            project = build.project
            image_uri = str(
                request.data.get("image_uri")
                or temporary_image_reference(
                    project.public_id,
                    build.public_id,
                    registry=settings.HARBOR_REGISTRY_URL if build.backend == "argo" else "",
                    registry_project=settings.HARBOR_USER_PROJECT,
                )
            )
            image_digest = str(request.data.get("image_digest", ""))[:255]
            if project.deletion_state != "active":
                build.status = "cancelled"
                build.image_uri = image_uri
                build.image_digest = image_digest
                build.error_message = "Project deletion is in progress; build output removed."
                build.completed_at = timezone.now()
                build.save(
                    update_fields=["status", "image_uri", "image_digest", "error_message", "completed_at", "updated_at"]
                )
                transaction.on_commit(lambda: cleanup_failed_build_artifacts.delay(str(build.public_id), True))
            else:
                build.package_uri = str(request.data.get("package_uri") or build.package_uri)
                build.save(update_fields=["package_uri", "updated_at"])
                build = register_successful_build(
                    build=build,
                    image_uri=image_uri,
                    image_digest=image_digest,
                    metrics_summary=_dict_payload(request.data.get("metrics_summary")),
                    params_summary=_dict_payload(request.data.get("params_summary")),
                    insights_summary=_dict_payload(request.data.get("insights_summary")),
                )
                build.completed_at = timezone.now()
                build.save(update_fields=["completed_at", "updated_at"])
        else:
            build.status = "failed"
            build.image_uri = str(request.data.get("image_uri", build.image_uri))
            build.image_digest = str(request.data.get("image_digest", build.image_digest))[:255]
            build.error_message = str(request.data.get("error_message", "Build failed."))[:12000]
            build.completed_at = timezone.now()
            build.save(
                update_fields=["status", "image_uri", "image_digest", "error_message", "completed_at", "updated_at"]
            )
            transaction.on_commit(
                lambda: cleanup_failed_build_artifacts.delay(str(build.public_id), bool(build.image_uri))
            )
        record_transition(
            build,
            build.status,
            source="webhook",
            reason="Build reporter confirmed failure" if build.status == "failed" else None,
        )
        return Response(
            {
                "status": build.status,
                "version_id": str(build.version.public_id) if build.version_id else None,
            }
        )
