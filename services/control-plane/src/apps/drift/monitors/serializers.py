from rest_framework import serializers

from apps.drift.models import DriftMonitor
from apps.drift.runs.serializers import DriftRunSerializer
from apps.registry.models import ModelVersion
from common.api.exceptions import Conflict


class DriftMonitorSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    version_id = serializers.UUIDField(source="version.public_id", read_only=True)
    project_id = serializers.UUIDField(source="version.project.public_id", read_only=True)
    deletion_requested = serializers.SerializerMethodField()
    version = serializers.SlugRelatedField(
        slug_field="public_id", queryset=ModelVersion.objects.none(), write_only=True
    )
    reference_file = serializers.FileField(write_only=True, required=False)
    csv_upload_token = serializers.CharField(write_only=True, required=False, max_length=2048)
    trigger_threshold = serializers.IntegerField(min_value=1, max_value=2147483647)
    runs = DriftRunSerializer(many=True, read_only=True)

    class Meta:
        model = DriftMonitor
        fields = (
            "id",
            "version",
            "version_id",
            "project_id",
            "reference_file",
            "csv_upload_token",
            "reference_name",
            "name",
            "trigger_threshold",
            "backend",
            "is_active",
            "deletion_requested",
            "runs",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("backend", "reference_name")
        validators = ()

    def get_deletion_requested(self, monitor):
        return monitor.deletion_requested or monitor.version.deletion_requested

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["version"].queryset = ModelVersion.objects.filter(project__owner=request.user)

    def validate(self, attrs):
        version = attrs.get("version", getattr(self.instance, "version", None))
        if self.instance and any(key in attrs for key in ("version", "reference_file", "csv_upload_token")):
            raise serializers.ValidationError("A monitor's version and reference snapshot are immutable.")
        name = attrs.get("name", getattr(self.instance, "name", ""))
        duplicate = DriftMonitor.objects.filter(version=version, name=name)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise Conflict(f"A drift monitor named {name} already exists for model version {version.version}.")
        return attrs
