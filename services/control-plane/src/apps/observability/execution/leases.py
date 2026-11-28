import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Case, CharField, F, Q, Value, When
from django.utils import timezone

from apps.observability.execution.resources import ARGO_SERVING_KINDS, WATCH_FIELDS, model_for, ownership_for

logger = logging.getLogger(__name__)


ACTIVE = {"queued", "running", "uploading", "cancelling"}


def _enqueue_observation_status():
    return Case(
        When(observation_status="cleanup_pending", then=Value("cleanup_pending")),
        default=Value("retrying"),
        output_field=CharField(),
    )


def ensure_watch(row):
    from django.db.models import Value
    from django.db.models.functions import Coalesce

    now = timezone.now()
    type(row).objects.filter(pk=row.pk).update(
        next_execution_check_at=now,
        dispatch_deadline_at=Coalesce(
            "dispatch_deadline_at", Value(now + timedelta(seconds=settings.EXECUTION_DISPATCH_TIMEOUT_SECONDS))
        ),
    )


def enqueue_safely(row, task):
    ensure_watch(row)
    try:
        result = task.delay(str(row.public_id))
        type(row).objects.filter(pk=row.pk).update(celery_task_id=result.id)
    except Exception as exc:
        type(row).objects.filter(pk=row.pk).update(
            observation_status=_enqueue_observation_status(),
            observation_error=f"Enqueue unavailable: {type(exc).__name__}",
        )
        logger.warning("Execution dispatch deferred kind=%s id=%s", row._meta.model_name, row.public_id)


def claim(kind, public_id=None):
    now = timezone.now()
    with transaction.atomic():
        if kind == "build":
            candidates = Q(backend="argo", status="building", deletion_state="active", project__deletion_state="active")
        elif kind == "deployment":
            candidates = Q(
                backend="argo",
                status__in=("deploying", "unconfirmed"),
                version__deletion_requested=False,
                version__project__deletion_state="active",
            )
        elif kind == "training":
            candidates = Q(status__in=ACTIVE) | Q(observation_status="cleanup_pending")
            candidates |= Q(deletion_requested_at__isnull=False)
            candidates &= Q(submitted_at__isnull=False)
        else:
            candidates = (Q(status__in=ACTIVE) | Q(observation_status="cleanup_pending")) & Q(
                monitor__deletion_requested=False, monitor__version__deletion_requested=False
            )
        rows = (
            model_for(kind)
            .objects.select_for_update(of=("self",), skip_locked=True)
            .filter(candidates)
            .filter(Q(execution_check_lease_until__isnull=True) | Q(execution_check_lease_until__lte=now))
        )
        if public_id:
            rows = rows.filter(public_id=public_id)
        else:
            rows = rows.filter(Q(next_execution_check_at__isnull=True) | Q(next_execution_check_at__lte=now))
        claimed = []
        lease_seconds = getattr(settings, "EXECUTION_CHECK_LEASE_SECONDS", 300)
        ordering = (F("next_execution_check_at").asc(nulls_first=True), "pk") if kind in ARGO_SERVING_KINDS else ("pk",)
        for row in rows.order_by(*ordering)[:100]:
            row.execution_check_token = uuid.uuid4()
            row.execution_check_lease_until = now + timedelta(seconds=lease_seconds)
            if kind in ARGO_SERVING_KINDS:
                row.save(update_fields=["execution_check_token", "execution_check_lease_until"])
            else:
                row.dispatch_deadline_at = row.dispatch_deadline_at or now + timedelta(
                    seconds=settings.EXECUTION_DISPATCH_TIMEOUT_SECONDS
                )
                row.save(update_fields=WATCH_FIELDS)
            claimed.append((str(row.public_id), str(row.execution_check_token)))
        return claimed


def _valid(row, token):
    return bool(
        row
        and str(row.execution_check_token) == str(token)
        and row.execution_check_lease_until
        and row.execution_check_lease_until > timezone.now()
    )


def _release(row, error=""):
    row.observation_failures = row.observation_failures + 1 if error else 0
    row.observation_error = error[:1000]
    if row.observation_status != "cleanup_pending":
        row.observation_status = "retrying" if error else "ok"
    delay = min(60, 5 * 2 ** min(max(row.observation_failures - 1, 0), 4)) if error else 15
    row.next_execution_check_at = timezone.now() + timedelta(seconds=delay)
    row.execution_check_token = None
    row.execution_check_lease_until = None
    row.save(update_fields=WATCH_FIELDS)


def signed_observation_token(kind, row, token):
    tenant, project_id = ownership_for(row, kind)
    return signing.dumps(
        {"kind": kind, "id": str(row.public_id), "lease": str(token), "tenant": tenant, "project": project_id},
        salt="execution-observation",
    )
