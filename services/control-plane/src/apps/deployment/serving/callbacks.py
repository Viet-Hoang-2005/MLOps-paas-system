from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.deployment.models import Deployment
from apps.deployment.serving.callback_tokens import valid_callback_token
from apps.deployment.serving.rollout_tasks import (
    _mark_deployment_succeeded,
    mark_argo_deployment_failed,
    stop_deployment,
)


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
        expected_workflow = f"deploy-{str(deployment_id).lower()}"
        if incoming not in {"succeeded", "failed", "error"} or workflow != expected_workflow:
            return Response({"detail": "A terminal workflow result and workflow name are required."}, status=400)
        with transaction.atomic():
            candidate = get_object_or_404(Deployment.objects.select_related("version"), public_id=deployment_id)
            ModelProject.objects.select_for_update().get(pk=candidate.version.project_id)
            deployment = get_object_or_404(
                Deployment.objects.select_for_update(of=("self",)).select_related("version__project"),
                public_id=deployment_id,
            )
            if deployment.backend != "argo":
                return Response({"detail": "This deployment does not use Argo."}, status=409)
            if deployment.status in {"succeeded", "failed", "stopped"}:
                if deployment.status in {"stopped", "failed"} and incoming == "succeeded":
                    # The workflow created its runtime after the stop or failure was recorded;
                    # nothing owns that runtime any more, so remove it. The status stays final.
                    transaction.on_commit(lambda: stop_deployment.delay(str(deployment.public_id)))
                return Response({"status": deployment.status, "duplicate": True})
            if deployment.version.project.deletion_state != "active":
                return Response({"status": deployment.status, "ignored": True})
            if deployment.external_deployment_id and deployment.external_deployment_id != workflow:
                return Response({"detail": "Workflow does not match this deployment."}, status=409)
            deployment.external_deployment_id = workflow
            deployment.save(update_fields=["external_deployment_id", "updated_at"])
            if incoming == "succeeded":
                _mark_deployment_succeeded(deployment)
                deployment.refresh_from_db()
                result = deployment.status
            else:
                result = "failed"
                mark_argo_deployment_failed(
                    deployment, f"Deployment workflow {workflow} finished with {incoming}. See execution logs."
                )
        try:
            from apps.notifications.events import notify_deployment_result

            notify_deployment_result(deployment)
        except Exception:
            pass
        return Response({"status": result})
