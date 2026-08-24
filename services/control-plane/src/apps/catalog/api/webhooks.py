from common.api.permissions import HasInternalWebhookSecret
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.catalog.services.deletion import mark_project_deletion_failed
from apps.catalog.tasks import complete_project_deletion


class ProjectDeletionWebhookEndpoint(APIView):
    """Trusted completion callback from the production Argo deletion workflow."""

    authentication_classes = ()
    permission_classes = (HasInternalWebhookSecret,)

    def post(self, request, project_id):
        project = get_object_or_404(
            ModelProject.objects.select_related("owner"),
            public_id=project_id,
        )
        if project.deletion_state == "deleted":
            return Response({"status": "deleted", "duplicate": True})
        if project.deletion_state != "deleting":
            return Response({"status": project.deletion_state, "ignored": True})

        incoming = str(request.data.get("status", "")).lower()
        if incoming in {"success", "succeeded", "completed", "deleted"}:
            complete_project_deletion.delay(str(project.public_id))
            return Response({"status": "deleting", "completion_enqueued": True})

        error = request.data.get("error_message") or request.data.get("error") or "Model cleanup failed."
        mark_project_deletion_failed(project, error)
        return Response({"status": "delete_failed"})
