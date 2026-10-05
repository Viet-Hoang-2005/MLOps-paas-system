"""Health observations never change lifecycle, Running pointers or drift state."""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.deployment.models import Deployment, Endpoint
from infrastructure.runtime_health import RuntimeHealthProbe

logger = logging.getLogger(__name__)


def effective_health(endpoint, now=None):
    now = now or timezone.now()
    if (
        endpoint.deployment.status != Deployment.Status.SUCCEEDED
        or not endpoint.last_checked_at
        or now - endpoint.last_checked_at > timedelta(seconds=settings.RUNTIME_HEALTH_STALE_SECONDS)
        or endpoint.last_checked_at > now + timedelta(seconds=5)
    ):
        return Endpoint.HealthStatus.UNKNOWN
    return endpoint.health_status


def running_endpoints():
    return Endpoint.objects.filter(
        deployment__status=Deployment.Status.SUCCEEDED,
        deployment__active_projects__is_active=True,
        deployment__active_projects__deletion_state="active",
    )


def dispatch_health_checks():
    from apps.deployment.health_tasks import probe_runtime_health

    now = timezone.now()
    cycle_start = now - timedelta(seconds=now.timestamp() % settings.RUNTIME_HEALTH_INTERVAL_SECONDS)
    count = 0
    with transaction.atomic():
        endpoints = list(
            running_endpoints()
            .filter(Q(health_check_lease_until__isnull=True) | Q(health_check_lease_until__lte=now))
            .filter(Q(last_checked_at__isnull=True) | Q(last_checked_at__lt=cycle_start))
            .select_related("deployment")
            .select_for_update(of=("self",), skip_locked=True)
            .order_by("pk")[:500]
        )
        for endpoint in endpoints:
            token = uuid.uuid4()
            endpoint.health_check_token = token
            endpoint.health_check_lease_until = now + timedelta(seconds=30)
            endpoint.save(update_fields=["health_check_token", "health_check_lease_until"])
            deployment_id = str(endpoint.deployment.public_id)

            def publish(deployment_id=deployment_id, token=token, endpoint_pk=endpoint.pk):
                try:
                    probe_runtime_health.apply_async(
                        args=[deployment_id, str(token)], queue="runtime-health", expires=15,
                    )
                except Exception:
                    Endpoint.objects.filter(pk=endpoint_pk, health_check_token=token).update(
                        health_check_token=None, health_check_lease_until=None,
                    )
                    logger.exception("Unable to enqueue runtime health probe for deployment %s", deployment_id)
                    raise

            transaction.on_commit(publish, robust=True)
            count += 1
    return count


def probe_running_health(deployment_id, token, probe=None):
    now = timezone.now()
    endpoint = (
        running_endpoints().select_related("deployment__version__project")
        .filter(deployment__public_id=deployment_id, health_check_token=token, health_check_lease_until__gt=now)
        .first()
    )
    if not endpoint:
        return "ignored"
    # A delivery token is single-use: atomically replace it with this probe's
    # ownership token before doing any I/O. Duplicate deliveries cannot both probe.
    probe_token = uuid.uuid4()
    # Keep the compare-and-swap predicate on the updated row, not inside a
    # joined/subquery update, so PostgreSQL rechecks it after a concurrent writer.
    claimed = Endpoint.objects.filter(
        pk=endpoint.pk, health_check_token=token, health_check_lease_until__gt=timezone.now(),
    ).update(health_check_token=probe_token)
    if not claimed:
        return "ignored"
    token = probe_token
    version = endpoint.deployment.version
    health = (probe or RuntimeHealthProbe()).check(
        url=endpoint.internal_url, flavor=version.flavor,
        project_id=version.project.public_id, version_id=version.public_id,
    )
    checked_at = timezone.now()
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().filter(pk=version.project_id).first()
        deployment = Deployment.objects.select_for_update().filter(pk=endpoint.deployment_id).first()
        current = Endpoint.objects.select_for_update().filter(pk=endpoint.pk).first()
        if not project or not deployment or not current:
            return "ignored"
        if (
            not project.is_active or project.deletion_state != "active"
            or project.active_deployment_id != deployment.pk
            or deployment.status != Deployment.Status.SUCCEEDED
            or str(current.health_check_token) != str(token)
            or not current.health_check_lease_until or current.health_check_lease_until <= timezone.now()
        ):
            return "ignored"
        previous = current.health_status
        current.health_status = health
        current.last_checked_at = checked_at
        current.health_check_token = None
        current.health_check_lease_until = None
        current.save(update_fields=[
            "health_status", "last_checked_at", "health_check_token", "health_check_lease_until", "updated_at",
        ])
        if previous != health:
            transaction.on_commit(lambda: logger.info(
                "Runtime health changed deployment=%s from=%s to=%s", deployment_id, previous, health,
            ))
    return health
