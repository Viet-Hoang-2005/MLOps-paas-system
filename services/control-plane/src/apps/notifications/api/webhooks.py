import logging
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from common.api.permissions import HasInternalWebhookSecret
from ..models import Notification
from ..services import create_notification

logger = logging.getLogger(__name__)
User = get_user_model()


class AlertWebhookEndpoint(APIView):
    """Webhook receiver for Prometheus Alertmanager alerts."""

    authentication_classes = ()
    permission_classes = (HasInternalWebhookSecret,)

    def post(self, request):
        alerts = request.data.get("alerts", [])
        if not isinstance(alerts, list):
            alerts = [request.data] if request.data else []

        created_count = 0
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            alert_status = alert.get("status", "firing")
            if alert_status != "firing":
                continue

            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            alertname = labels.get("alertname", "Alert")
            severity = labels.get("severity", "warning")
            project_id = labels.get("project_id")
            model_version_id = labels.get("model_version_id")

            title = annotations.get("summary") or f"Alert: {alertname}"
            description = annotations.get("description") or title
            level = (
                Notification.Level.ERROR
                if severity == "critical"
                else Notification.Level.WARNING
            )

            # Route to model project owner if project_id is present
            if project_id:
                try:
                    project = ModelProject.objects.select_related("owner").filter(public_id=project_id).first()
                except Exception:
                    project = None

                if project and project.owner:
                    link = f"/dashboard/projects/{project.public_id}/monitoring"
                    create_notification(
                        user=project.owner,
                        type=Notification.Type.ALERT,
                        level=level,
                        title=title,
                        message=description,
                        link=link,
                        metadata={
                            "alertname": alertname,
                            "severity": severity,
                            "project_id": str(project_id),
                            "model_version_id": str(model_version_id) if model_version_id else "",
                        },
                    )
                    created_count += 1
            else:
                # System-level alerts notify active staff/admin users
                staff_users = User.objects.filter(is_active=True, is_staff=True)[:10]
                for admin_user in staff_users:
                    create_notification(
                        user=admin_user,
                        type=Notification.Type.ALERT,
                        level=level,
                        title=title,
                        message=description,
                        link="/dashboard/overview",
                        metadata={"alertname": alertname, "severity": severity},
                    )
                    created_count += 1

        return Response({"status": "received", "created_notifications": created_count}, status=status.HTTP_200_OK)
