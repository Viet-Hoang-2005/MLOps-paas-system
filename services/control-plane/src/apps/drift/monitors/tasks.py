from celery import shared_task


@shared_task(name="apps.drift.tasks.cleanup_drift_monitor_task", ignore_result=True)
def cleanup_drift_monitor_task(monitor_id):
    from apps.drift.models import DriftMonitor
    from apps.drift.monitors.deletion import delete_drift_monitor

    monitor = DriftMonitor.objects.filter(public_id=monitor_id, deletion_requested=True).first()
    if monitor is None:
        return "missing"
    delete_drift_monitor(monitor)
    return "deleted"
