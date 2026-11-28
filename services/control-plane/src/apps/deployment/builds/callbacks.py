import re

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.deployment.builds.cleanup import cleanup_failed_build_artifacts, delete_build
from apps.deployment.builds.registration import complete_reported_build, expected_build_image, valid_build_result
from apps.deployment.models import Build
from common.api.permissions import HasInternalWebhookSecret
from common.telemetry.logging import record_transition


class BuildWebhookEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (HasInternalWebhookSecret,)

    @transaction.atomic
    def post(self, request, build_id):
        candidate = get_object_or_404(Build, public_id=build_id)
        ModelProject.objects.select_for_update().get(pk=candidate.project_id)
        build = (
            # The project is already locked; version is nullable, so PostgreSQL
            # must not lock the nullable side of its LEFT OUTER JOIN.
            Build.objects.select_for_update(of=("self",))
            .select_related("project", "project__owner", "version")
            .get(pk=candidate.pk)
        )
        incoming = str(request.data.get("status", "")).lower()
        if incoming not in {"success", "succeeded", "ready", "completed", "failed", "error"}:
            return Response({"detail": "A terminal build result is required."}, status=400)
        if request.data.get("build_id") and str(request.data["build_id"]) != str(build.public_id):
            return Response({"detail": "Build identity does not match the callback path."}, status=400)
        if build.status in {"ready", "failed", "cancelled"}:
            if build.backend == "argo":
                build.execution_completed_at = timezone.now()
                build.save(update_fields=["execution_completed_at"])
            if build.deletion_state != "active":
                transaction.on_commit(lambda: delete_build.delay(str(build.public_id)))
            elif build.backend == "argo" and build.status == "cancelled" and not build.version_id:
                # The workflow outlived the cancel and may have published an image and package
                # after the cancel-time cleanup ran. The image reference is server-generated.
                if not build.image_uri:
                    build.image_uri = expected_build_image(build)
                    build.save(update_fields=["image_uri"])
                transaction.on_commit(lambda: cleanup_failed_build_artifacts.delay(str(build.public_id), True))
            return Response(
                {
                    "status": build.status,
                    "version_id": str(build.version.public_id) if build.version_id else None,
                    "duplicate": True,
                }
            )
        # The only image a build may publish is the one named after its own identity; a
        # reporter-supplied reference is never trusted, whichever backend ran the build.
        expected_image = expected_build_image(build)
        will_register = (
            incoming in {"success", "succeeded", "ready", "completed"}
            and build.deletion_state == "active"
            and build.project.deletion_state == "active"
        )
        if will_register and not valid_build_result(build, request.data, expected_image):
            return Response(
                {"detail": "A valid build-scoped image, digest and package manifest are required."}, status=400
            )
        if build.backend == "docker" and build.execution_deadline_at and build.execution_deadline_at <= timezone.now():
            return Response({"detail": "Build result arrived after the execution deadline."}, status=409)
        build.execution_completed_at = timezone.now()
        build.save(update_fields=["execution_completed_at"])
        if incoming in {"success", "succeeded", "ready", "completed"}:
            project = build.project
            image_uri = expected_image
            image_digest = str(request.data.get("image_digest", ""))[:255]
            if project.deletion_state != "active" or build.deletion_state != "active":
                build.status = "cancelled"
                build.image_uri = image_uri
                build.image_digest = image_digest
                build.error_message = "Project deletion is in progress; build output removed."
                build.completed_at = timezone.now()
                build.save(
                    update_fields=["status", "image_uri", "image_digest", "error_message", "completed_at", "updated_at"]
                )
                if build.deletion_state != "active":
                    transaction.on_commit(lambda: delete_build.delay(str(build.public_id)))
                else:
                    transaction.on_commit(lambda: cleanup_failed_build_artifacts.delay(str(build.public_id), True))
            else:
                build = complete_reported_build(build, request.data, expected_image)
        else:
            build.status = "failed"
            # Cleanup deletes build.image_uri from the registry, so it must stay build-scoped.
            if request.data.get("image_uri") == expected_image:
                build.image_uri = expected_image
            if re.fullmatch(r"sha256:[a-f0-9]{64}", str(request.data.get("image_digest", ""))):
                build.image_digest = str(request.data["image_digest"])
            build.error_message = str(request.data.get("error_message", "Build failed."))[:12000]
            build.completed_at = timezone.now()
            if build.backend == "argo":
                build.next_execution_check_at = build.completed_at
            build.save(
                update_fields=[
                    "status", "image_uri", "image_digest", "error_message", "completed_at", "next_execution_check_at",
                    "updated_at",
                ]
            )
            if build.deletion_state != "active":
                transaction.on_commit(lambda: delete_build.delay(str(build.public_id)))
            else:
                transaction.on_commit(
                    lambda: cleanup_failed_build_artifacts.delay(str(build.public_id), bool(build.image_uri))
                )
        record_transition(
            build,
            build.status,
            source="webhook",
            reason="Build reporter confirmed failure" if build.status == "failed" else None,
        )
        try:
            from apps.notifications.events import notify_build_result

            notify_build_result(build)
        except Exception:
            pass
        return Response(
            {
                "status": build.status,
                "version_id": str(build.version.public_id) if build.version_id else None,
            }
        )
