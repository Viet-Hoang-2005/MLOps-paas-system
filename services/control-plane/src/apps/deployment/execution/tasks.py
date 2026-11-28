from celery import shared_task

from apps.deployment.execution.local_watcher import check_execution, dispatch_execution_checks


@shared_task(name="apps.deployment.execution_tasks.scan_local_executions", ignore_result=True, expires=10, soft_time_limit=20, time_limit=25)
def scan_local_executions():
    return dispatch_execution_checks()


@shared_task(name="apps.deployment.execution_tasks.check_local_execution", ignore_result=True, expires=10, soft_time_limit=20, time_limit=25)
def check_local_execution(kind, public_id, token):
    return check_execution(kind, public_id, token)
