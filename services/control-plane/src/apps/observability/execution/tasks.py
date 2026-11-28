from celery import shared_task


@shared_task(name="apps.observability.tasks.scan_job_executions", ignore_result=True)
def scan_job_executions():
    from apps.training.workspace.runs import recover_preparations

    recover_preparations()
    from apps.observability.execution.reconciliation import _reconcile_argo_deadlines, scan

    _reconcile_argo_deadlines()
    return scan()


@shared_task(
    name="apps.observability.tasks.reconcile_job_execution", ignore_result=True, soft_time_limit=50, time_limit=55
)
def reconcile_job_execution(kind, public_id, token):
    from apps.observability.execution.reconciliation import reconcile

    return reconcile(kind, public_id, token)
