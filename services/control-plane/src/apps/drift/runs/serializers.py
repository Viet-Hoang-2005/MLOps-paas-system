from rest_framework import serializers

from apps.drift.models import DriftRun
from apps.drift.runs.reports import report_uri_for_run


class DriftRunSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    report_html_uri = serializers.SerializerMethodField()
    report_json_uri = serializers.SerializerMethodField()
    summary_uri = serializers.SerializerMethodField()
    production_records = serializers.SerializerMethodField()

    def get_report_html_uri(self, run):
        return report_uri_for_run(run, "report_html_uri")

    def get_report_json_uri(self, run):
        return report_uri_for_run(run, "report_json_uri")

    def get_summary_uri(self, run):
        return report_uri_for_run(run, "summary_uri")

    def get_production_records(self, run):
        if isinstance(run.summary, dict):
            for key in ("production_records", "samples", "production_samples", "records_count"):
                val = run.summary.get(key)
                if val is not None:
                    return val
        try:
            from apps.production.models import PredictionRecord

            return PredictionRecord.objects.filter(
                project=run.monitor.version.project,
                model_version=run.monitor.version,
                created_at__lte=run.created_at,
            ).count()
        except Exception:
            return None

    class Meta:
        model = DriftRun
        fields = (
            "id",
            "status",
            "observation_status",
            "observation_error",
            "execution_deadline_at",
            "runtime_started_at",
            "celery_task_id",
            "external_run_id",
            "current_data_uri",
            "report_html_uri",
            "report_json_uri",
            "summary_uri",
            "production_records",
            "drift_score",
            "has_drift",
            "summary",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
        )
