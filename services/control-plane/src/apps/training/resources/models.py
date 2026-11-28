from django.conf import settings
from django.db import models


class LocalTrainingPool(models.Model):
    daemon_id = models.CharField(max_length=128, unique=True)

    def __str__(self):
        return self.daemon_id


class LocalTrainingReservation(models.Model):
    pool = models.ForeignKey(LocalTrainingPool, on_delete=models.PROTECT, related_name="reservations")
    job_id = models.UUIDField(unique=True)
    vcpu = models.PositiveIntegerField()
    memory_mb = models.PositiveIntegerField()
    active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return str(self.job_id)


class TrainingQuotaReservation(models.Model):
    """Durable usage survives deletion of the job and its project."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_quota_reservations"
    )
    job_id = models.UUIDField(unique=True)
    resource = models.CharField(max_length=16)
    submitted_at = models.DateTimeField()
    dispatch_deadline_at = models.DateTimeField()
    max_runtime_seconds = models.PositiveIntegerField()
    started_at = models.DateTimeField(null=True, blank=True)
    runtime_finished_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return f"{self.job_id}:{self.resource}"


class TrainingQuotaWeek(models.Model):
    reservation = models.ForeignKey(TrainingQuotaReservation, on_delete=models.CASCADE, related_name="weeks")
    week_start = models.DateTimeField()
    reserved_seconds = models.PositiveIntegerField(default=0)
    used_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["reservation", "week_start"], name="training_quota_job_week_unique")
        ]
        indexes = [models.Index(fields=["week_start"], name="training_quota_week_idx")]

    def __str__(self):
        return f"{self.reservation_id}:{self.week_start}"
