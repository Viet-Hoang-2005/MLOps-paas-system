"""Durable per-account weekly training reservations and usage."""

import math
from datetime import timedelta, timezone as datetime_timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone

from apps.training.models import TrainingQuotaReservation, TrainingQuotaWeek
from common.api.exceptions import Conflict, ServiceUnavailable

WEEK = timedelta(days=7)


def week_start(value):
    value = value.astimezone(tz=datetime_timezone.utc)
    return (value - timedelta(days=value.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def limits():
    return {"cpu_small": None, "cpu_medium": settings.TRAINING_CPU_MEDIUM_WEEKLY_SECONDS,
            "cpu_large": settings.TRAINING_CPU_LARGE_WEEKLY_SECONDS, "t4": settings.TRAINING_GPU_T4_WEEKLY_SECONDS,
            "a10g": settings.TRAINING_GPU_A10G_WEEKLY_SECONDS}


def resource_for(job):
    if job.accelerator_type == "gpu":
        return job.accelerator_model
    return {(1, 2048): "cpu_small", (2, 4096): "cpu_medium", (4, 8192): "cpu_large"}[(job.vcpu, job.memory_mb)]


def _window_overlaps(earliest, latest, duration):
    """Maximum possible overlap for any start in [earliest, latest]."""
    end = latest + timedelta(seconds=duration)
    cursor = week_start(earliest)
    result = {}
    while cursor < end:
        finish = cursor + WEEK
        overlap = min(duration, max(0, math.ceil((min(end, finish) - max(earliest, cursor)).total_seconds())))
        if overlap:
            result[cursor] = overlap
        cursor = finish
    return result


def lock_owner(owner_id):
    return get_user_model().objects.select_for_update().get(pk=owner_id)


class QuotaExceeded(Conflict):
    default_code = "training_quota_exceeded"


class TrainingConcurrencyExceeded(Conflict):
    default_code = "training_concurrency_exceeded"


def reserve(job):
    """Caller holds the owner lock within the submit transaction."""
    if job.backend != "argo":
        return
    if not settings.TRAINING_EXECUTION_WATCH_ENABLED:
        raise ServiceUnavailable("Production training requires execution monitoring.")
    if TrainingQuotaReservation.objects.filter(owner_id=job.owner_id, active=True).exists():
        raise TrainingConcurrencyExceeded("Another training job is still active or being cleaned up.")
    now = timezone.now()
    deadline = now + timedelta(seconds=settings.EXECUTION_DISPATCH_TIMEOUT_SECONDS)
    resource = resource_for(job)
    limit = limits()[resource]
    overlaps = _window_overlaps(now, deadline, job.max_runtime_seconds)
    for week, amount in overlaps.items():
        used = TrainingQuotaWeek.objects.filter(reservation__owner_id=job.owner_id,
            reservation__resource=resource, week_start=week).aggregate(
                used=Sum("used_seconds"), reserved=Sum("reserved_seconds"))
        remaining = None if limit is None else max(0, limit - (used["used"] or 0) - (used["reserved"] or 0))
        if remaining is not None and amount > remaining:
            raise QuotaExceeded({"resource": resource, "required_seconds": amount,
                                 "remaining_seconds": remaining, "reset_at": (week + WEEK).isoformat()})
    reservation = TrainingQuotaReservation.objects.create(owner_id=job.owner_id, job_id=job.public_id,
        resource=resource, submitted_at=now, dispatch_deadline_at=deadline, max_runtime_seconds=job.max_runtime_seconds)
    TrainingQuotaWeek.objects.bulk_create([TrainingQuotaWeek(reservation=reservation, week_start=week,
        reserved_seconds=amount) for week, amount in overlaps.items()])
    job.dispatch_deadline_at = deadline


def require_reservation(job):
    if job.backend == "argo" and not TrainingQuotaReservation.objects.filter(job_id=job.public_id, active=True).exists():
        raise ServiceUnavailable("Training quota reservation is unavailable.")


def update_observation(job, *, started_at=None, finished_at=None, stopped=False):
    """Caller holds owner and job locks; only a confirmed stop releases reservation."""
    reservation = TrainingQuotaReservation.objects.select_for_update().filter(job_id=job.public_id, active=True).first()
    if not reservation:
        return True
    if started_at and not reservation.started_at:
        reservation.started_at = started_at
        overlaps = _window_overlaps(started_at, started_at, reservation.max_runtime_seconds)
        for row in reservation.weeks.all():
            row.reserved_seconds = overlaps.pop(row.week_start, 0)
            row.save(update_fields=["reserved_seconds"])
        for week, amount in overlaps.items():
            TrainingQuotaWeek.objects.create(reservation=reservation, week_start=week, reserved_seconds=amount)
        reservation.save(update_fields=["started_at"])
    if finished_at and not reservation.runtime_finished_at:
        reservation.runtime_finished_at = finished_at
        reservation.save(update_fields=["runtime_finished_at"])
    if not stopped:
        return True
    if not reservation.started_at and job.external_job_id:
        return False  # Runtime creation was attempted but no trustworthy start is available.
    end = reservation.runtime_finished_at or finished_at or timezone.now()
    overlaps = _window_overlaps(reservation.started_at, reservation.started_at,
        max(0, math.ceil((end - reservation.started_at).total_seconds()))) if reservation.started_at else {}
    for row in reservation.weeks.all():
        row.used_seconds = overlaps.pop(row.week_start, 0)
        row.reserved_seconds = 0
        row.save(update_fields=["used_seconds", "reserved_seconds"])
    for week, amount in overlaps.items():
        TrainingQuotaWeek.objects.create(reservation=reservation, week_start=week, used_seconds=amount)
    reservation.active, reservation.stopped_at = False, end
    reservation.save(update_fields=["active", "stopped_at"])
    return True


def usage(user):
    now = timezone.now()
    current = week_start(now)
    backend = settings.TRAINING_BACKEND
    values = []
    available = limits() if backend == "argo" else {"cpu_small": None, "cpu_medium": None, "cpu_large": None, "gpu_local": None}
    for resource, limit in available.items():
        rows = TrainingQuotaWeek.objects.filter(reservation__owner=user, reservation__resource=resource,
                                                week_start=current).select_related("reservation") if backend == "argo" else []
        used = reserved = 0
        for row in rows:
            live = 0
            if row.reservation.active and row.reservation.started_at:
                start = max(row.reservation.started_at, current)
                observed_end = row.reservation.runtime_finished_at or now
                live = max(0, math.floor((min(observed_end, now, current + WEEK) - start).total_seconds()))
            used += row.used_seconds + live
            reserved += max(0, row.reserved_seconds - live)
        effective_limit = limit if backend == "argo" else None
        values.append({"resource": resource, "limit_seconds": effective_limit, "used_seconds": used,
                       "reserved_seconds": reserved,
                       "remaining_seconds": max(0, effective_limit - used - reserved) if effective_limit is not None else None})
    return {"backend": backend, "week_start": current.isoformat(), "reset_at": (current + WEEK).isoformat(),
            "active_jobs_count": TrainingQuotaReservation.objects.filter(owner=user, active=True).count() if backend == "argo" else None,
            "max_active_jobs": 1 if backend == "argo" else None, "resources": values}
