"""Append-only lifecycle audit shared by training and registry."""

from apps.observability.models import LifecycleEvent


def record_event(*, project, aggregate_type, aggregate_id, event_type, message="", actor=None,
                 from_state="", to_state="", metadata=None, idempotency_key="", correlation_id=None,
                 maintenance_id=None):
    return LifecycleEvent.objects.create(
        project=project,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor=actor,
        event_type=event_type,
        message=message,
        from_state=from_state,
        to_state=to_state,
        metadata=metadata or {},
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        maintenance_id=maintenance_id,
    )


def has_event(*, aggregate_type, aggregate_id, idempotency_key):
    return bool(idempotency_key) and LifecycleEvent.objects.filter(
        aggregate_type=aggregate_type, aggregate_id=aggregate_id, idempotency_key=idempotency_key
    ).exists()


def events_for_aggregate(*, aggregate_type, aggregate_id):
    return LifecycleEvent.objects.filter(aggregate_type=aggregate_type, aggregate_id=aggregate_id).order_by("created_at")


def record_training_event(*, job, event_type, message, metadata=None, idempotency_key=""):
    return record_event(
        project=job.project,
        aggregate_type="training_job",
        aggregate_id=job.public_id,
        event_type=event_type,
        message=message,
        metadata=metadata,
        idempotency_key=idempotency_key,
    )


def record_registry_event(*, version, event_type, actor=None, from_state="", to_state="", metadata=None):
    return record_event(
        project=version.project,
        aggregate_type="model_version",
        aggregate_id=version.public_id,
        event_type=event_type,
        actor=actor,
        from_state=from_state,
        to_state=to_state,
        metadata=metadata,
    )
