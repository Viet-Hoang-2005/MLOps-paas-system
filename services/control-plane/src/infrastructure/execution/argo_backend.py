from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.observability.execution.argo_stops import stop_payload
from infrastructure.execution.argo_client import ArgoWebhookClient
from infrastructure.storage import S3Storage


class _ArgoBackend:
    setting_name = ""
    # Without the execution watcher, terminal status arrives only via callbacks.
    reports_by_callback = True

    def __init__(self, client=None, storage=None):
        self.client = client or ArgoWebhookClient()
        self.storage = storage or S3Storage()

    def trigger(self, payload):
        response = self.client.trigger(getattr(settings, self.setting_name), payload)
        return {"dispatched": True, "response": response}

    def poll(self, resource):
        # Actual cluster observations arrive through the scoped reconcile workflow.
        return {"status": "not_found"}

    def request_runtime_stop(self, resource, kind):
        pending = type(resource).objects.filter(pk=resource.pk, argo_stop_confirmed_at__isnull=True)
        needs_stop = pending.update(execution_stop_requested=True) if kind == "drift" else pending.exists()
        if not needs_stop:
            return {"confirmed": True}
        key = f"argo-runtime-stop:{kind}:{resource.public_id}"
        if cache.add(key, True, timeout=150):
            try:
                self.client.trigger(
                    settings.ARGO_RECONCILE_WEBHOOK_URL,
                    stop_payload(resource, kind, settings.CONTROL_PLANE_INTERNAL_URL),
                )
            except Exception:
                cache.delete(key)
                raise
        return {"confirmed": False}

    def persist_dispatch(self, resource, **fields):
        from common.api.exceptions import Conflict

        project = resource.project if hasattr(resource, "project") else resource.monitor.version.project
        with transaction.atomic():
            locked_project = type(project).objects.select_for_update().get(pk=project.pk) if project else None
            rows = (
                type(resource)
                .objects.filter(pk=resource.pk)
                .exclude(status__in=["cancelling", "cancelled", "failed", "completed"])
                .filter(execution_stop_requested=False)
            )
            if resource.execution_check_token:
                rows = rows.filter(
                    execution_check_token=resource.execution_check_token, execution_check_lease_until__gt=timezone.now()
                )
            if (locked_project and locked_project.deletion_state != "active") or not rows.update(**fields):
                raise Conflict("Execution is inactive or dispatch lease expired.")

    def reconcile(self, resource, kind, token, stop=False):
        from apps.observability.execution.leases import signed_observation_token
        from apps.observability.execution.resources import ownership_for

        tenant, project_id = ownership_for(resource, kind)
        return self.client.trigger(
            settings.ARGO_RECONCILE_WEBHOOK_URL,
            {
                "kind": kind,
                "resource_id": str(resource.public_id),
                "project_id": project_id,
                "tenant_id": tenant,
                "stop": stop,
                "callback_url": f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/executions/{kind}/{resource.public_id}/observations/",
                "callback_token": signed_observation_token(kind, resource, token),
            },
        )
