from django.db import models


class ExecutionWatch(models.Model):
    next_execution_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    execution_check_token = models.UUIDField(null=True, blank=True)
    execution_check_lease_until = models.DateTimeField(null=True, blank=True)
    dispatch_deadline_at = models.DateTimeField(null=True, blank=True)
    execution_deadline_at = models.DateTimeField(null=True, blank=True)
    runtime_started_at = models.DateTimeField(null=True, blank=True)
    execution_stop_requested = models.BooleanField(default=False)
    observation_status = models.CharField(max_length=20, default="ok", choices=[
        ("ok", "OK"), ("retrying", "Retrying"), ("cleanup_pending", "Cleanup pending"),
    ])
    observation_error = models.CharField(max_length=1000, blank=True)
    observation_failures = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
