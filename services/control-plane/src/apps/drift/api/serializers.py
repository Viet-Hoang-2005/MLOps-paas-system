from rest_framework import serializers

from apps.drift.models import DriftMonitor, DriftRun
from apps.registry.models import ModelVersion
from common.api.exceptions import Conflict


class DriftRunSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = DriftRun
        fields = (
            "id",
            "status",
            "celery_task_id",
            "external_run_id",
            "current_data_uri",
            "report_html_uri",
            "report_json_uri",
            "summary_uri",
            "drift_score",
            "has_drift",
            "summary",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
        )


class DriftMonitorSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    version_id = serializers.UUIDField(source="version.public_id", read_only=True)
    project_id = serializers.UUIDField(source="version.project.public_id", read_only=True)
    version = serializers.SlugRelatedField(
        slug_field="public_id", queryset=ModelVersion.objects.none(), write_only=True
    )
    reference_snapshot_id = serializers.UUIDField(source="reference_snapshot.public_id", read_only=True, allow_null=True)
    runs = DriftRunSerializer(many=True, read_only=True)

    class Meta:
        model = DriftMonitor
        fields = (
            "id",
            "version",
            "version_id",
            "project_id",
            "reference_snapshot_id",
            "name",
            "trigger_threshold",
            "backend",
            "is_active",
            "runs",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("backend",)
        validators = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["version"].queryset = ModelVersion.objects.filter(project__owner=request.user)

    def validate(self, attrs):
        version = attrs.get("version", getattr(self.instance, "version", None))
        name = attrs.get("name", getattr(self.instance, "name", ""))
        if not version or not version.reference_snapshot_id:
            raise serializers.ValidationError({"version": "This version has no immutable reference snapshot."})
        attrs["reference_snapshot"] = version.reference_snapshot

        duplicate = DriftMonitor.objects.filter(version=version, name=name)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise Conflict(f"A drift monitor named {name} already exists for model version {version.version}.")
        return attrs
