import hashlib
import logging

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.notifications.delivery import create_notification
from apps.notifications.models import Notification
from common.api.permissions import HasInternalWebhookSecret

logger = logging.getLogger(__name__)
User = get_user_model()
_ALERT_DEDUPE_TTL_SECONDS = 4 * 3600


def _alert_fingerprint(alert, alertname, project_id, severity):
    fp = str(alert.get("fingerprint") or "").strip()
    if fp:
        return fp[:64]
    raw = f"{alertname}:{project_id or ''}:{severity}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _dedupe_key(user_id, fingerprint):
    return f"alert-dedupe:{user_id}:{fingerprint}"


def _is_duplicate_alert(user, fingerprint):
    if cache.get(_dedupe_key(user.pk, fingerprint)):
        return True
    return Notification.objects.filter(
        user=user,
        type=Notification.Type.ALERT,
        is_read=False,
        metadata__fingerprint=fingerprint,
    ).exists()


def _mark_alert_seen(user, fingerprint):
    cache.set(_dedupe_key(user.pk, fingerprint), 1, timeout=_ALERT_DEDUPE_TTL_SECONDS)


def _clear_alert_seen(user, fingerprint):
    cache.delete(_dedupe_key(user.pk, fingerprint))


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
            labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
            annotations = alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
            alertname = labels.get("alertname", "Alert")
            severity = labels.get("severity", "warning")
            project_id = labels.get("project_id")
            model_version_id = labels.get("model_version_id")
            label_tenant_id = str(labels.get("tenant_id") or "").strip()
            fingerprint = _alert_fingerprint(alert, alertname, project_id, severity)

            # Resolve target recipients
            recipients = []
            link = "/dashboard/overview"
            if project_id:
                try:
                    project = (
                        ModelProject.objects.select_related("owner")
                        .filter(public_id=project_id, is_active=True, deletion_state="active", owner__is_active=True)
                        .first()
                    )
                except Exception:
                    project = None
                if not project or not project.owner:
                    continue
                if label_tenant_id and label_tenant_id != project.owner.tenant_id:
                    logger.warning(
                        "Alert webhook tenant mismatch: alert=%s project=%s label_tenant=%s owner_tenant=%s",
                        alertname,
                        project_id,
                        label_tenant_id,
                        project.owner.tenant_id,
                    )
                    continue
                recipients = [project.owner]
                link = f"/dashboard/projects/{project.public_id}/overview"
            else:
                recipients = list(User.objects.filter(is_active=True, is_staff=True)[:10])

            if alert_status == "resolved":
                for recipient in recipients:
                    _clear_alert_seen(recipient, fingerprint)
                continue
            if alert_status != "firing":
                continue

            title = annotations.get("summary") or f"Alert: {alertname}"
            description = annotations.get("description") or title
            level = Notification.Level.ERROR if severity == "critical" else Notification.Level.WARNING
            metadata = {
                "alertname": alertname,
                "severity": severity,
                "fingerprint": fingerprint,
                "starts_at": str(alert.get("startsAt") or ""),
            }
            if project_id:
                metadata["project_id"] = str(project_id)
                metadata["model_version_id"] = str(model_version_id) if model_version_id else ""

            for recipient in recipients:
                if _is_duplicate_alert(recipient, fingerprint):
                    continue
                create_notification(
                    user=recipient,
                    type=Notification.Type.ALERT,
                    level=level,
                    title=title,
                    message=description,
                    link=link,
                    metadata=metadata,
                )
                _mark_alert_seen(recipient, fingerprint)
                created_count += 1

        return Response({"status": "received", "created_notifications": created_count}, status=status.HTTP_200_OK)
