from common.api.permissions import HasInternalWebhookSecret
from common.logging import record_transition
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from infrastructure.execution.image_references import temporary_image_reference
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.deployment.models import Build
from apps.deployment.tasks import cleanup_failed_build_artifacts
from apps.registry.services.versions import register_successful_build


def _dict_payload(value):
    return value if isinstance(value, dict) else {}


class BuildWebhookEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (HasInternalWebhookSecret,)

    def post(self, request, build_id):
        build = Build.objects.select_related("project", "project__owner", "version").get(public_id=build_id)
        incoming = str(request.data.get("status", "")).lower()
        if build.status in {"ready", "failed", "cancelled"}:
            return Response({
                "status": build.status,
                "version_id": str(build.version.public_id) if build.version_id else None,
                "duplicate": True,
            })
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
                build.save(update_fields=[
                    "status", "image_uri", "image_digest", "error_message", "completed_at", "updated_at"
                ])
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
            build.save(update_fields=[
                "status", "image_uri", "image_digest", "error_message", "completed_at", "updated_at"
            ])
            transaction.on_commit(
                lambda: cleanup_failed_build_artifacts.delay(str(build.public_id), bool(build.image_uri))
            )
        record_transition(
            build, build.status, source="webhook",
            reason="Build reporter confirmed failure" if build.status == "failed" else None,
        )
        return Response({
            "status": build.status,
            "version_id": str(build.version.public_id) if build.version_id else None,
        })
