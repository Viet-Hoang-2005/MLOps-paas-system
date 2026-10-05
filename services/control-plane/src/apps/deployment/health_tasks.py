from celery import shared_task

from apps.deployment.services.runtime_health import dispatch_health_checks, probe_running_health


@shared_task(ignore_result=True, expires=15, soft_time_limit=8, time_limit=10)
def scan_runtime_health():
    return dispatch_health_checks()


@shared_task(ignore_result=True, expires=15, soft_time_limit=8, time_limit=10)
def probe_runtime_health(deployment_id, token):
    return probe_running_health(deployment_id, token)
