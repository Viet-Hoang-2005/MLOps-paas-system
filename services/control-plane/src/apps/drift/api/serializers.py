from common.api.exceptions import Conflict
from rest_framework import serializers

from apps.catalog.models import WorkspaceAsset
from apps.drift.models import DriftMonitor, DriftRun
from apps.registry.models import ModelVersion


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
    reference_asset_id = serializers.UUIDField(source="reference_asset.public_id", read_only=True)
    reference_asset_name = serializers.CharField(source="reference_asset.relative_path", read_only=True)
    reference_asset = serializers.SlugRelatedField(
        slug_field="public_id", queryset=WorkspaceAsset.objects.none(), write_only=True
    )
    runs = DriftRunSerializer(many=True, read_only=True)

    class Meta:
        model = DriftMonitor
        fields = (
            "id",
            "version",
            "version_id",
            "project_id",
            "reference_asset",
            "reference_asset_id",
            "reference_asset_name",
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
            self.fields["reference_asset"].queryset = WorkspaceAsset.objects.filter(
                project__owner=request.user, kind="data"
            )

    def validate(self, attrs):
        version = attrs.get("version", getattr(self.instance, "version", None))
        reference_asset = attrs.get("reference_asset", getattr(self.instance, "reference_asset", None))
        name = attrs.get("name", getattr(self.instance, "name", ""))
        if version.project_id != reference_asset.project_id:
            raise serializers.ValidationError("Version and reference data must belong to the same project.")
        duplicate = DriftMonitor.objects.filter(version=version, name=name)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise Conflict(f'A drift monitor named {name} already exists for model version {version.version}.')
        return attrs
