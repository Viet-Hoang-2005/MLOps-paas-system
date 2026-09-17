from rest_framework import serializers

from apps.observability.models import LifecycleEvent
from apps.observability.services.lifecycle import events_for_aggregate
from apps.registry.models import ModelArtifact, ModelMetric, ModelVersion, RegistryAlias
from apps.training.models import TrainingJob


class ModelArtifactSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = ModelArtifact
        fields = ("id", "kind", "name", "uri", "checksum", "size_bytes", "content_type", "metadata", "created_at")


class ModelVersionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    project_id = serializers.UUIDField(source="project.public_id", read_only=True)
    source_job_id = serializers.SerializerMethodField()
    source_job = serializers.SlugRelatedField(
        slug_field="public_id", queryset=TrainingJob.objects.none(), required=False, allow_null=True, write_only=True
    )
    source_artifact = serializers.FileField(write_only=True, required=False)
    artifacts = ModelArtifactSerializer(many=True, read_only=True)
    metrics = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()

    class Meta:
        model = ModelVersion
        fields = (
            "id",
            "project_id",
            "version",
            "source_job",
            "source_job_id",
            "source_artifact",
            "requirements_snapshot",
            "flavor",
            "stage",
            "deployability",
            "deployability_reason",
            "metrics_summary",
            "params_summary",
            "insights_summary",
            "artifacts",
            "metrics",
            "events",
            "registered_at",
        )
        read_only_fields = (
            "requirements_snapshot",
            "deployability",
            "deployability_reason",
            "metrics_summary",
            "params_summary",
            "insights_summary",
            "registered_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        project = self.context.get("project")
        if request and project:
            self.fields["source_job"].queryset = TrainingJob.objects.filter(project=project, status="completed")

    def get_metrics(self, instance):
        return ModelMetricSerializer(instance.metrics.all(), many=True).data

    @staticmethod
    def get_source_job_id(instance):
        return instance.source_job_reference or (
            instance.source_job.public_id if instance.source_job_id else None
        )

    def get_events(self, instance):
        return RegistryEventSerializer(
            events_for_aggregate(aggregate_type="model_version", aggregate_id=instance.public_id), many=True
        ).data


class RegistryAliasSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    version_id = serializers.UUIDField(source="version.public_id", read_only=True)
    version = serializers.SlugRelatedField(
        slug_field="public_id", queryset=ModelVersion.objects.none(), write_only=True
    )

    class Meta:
        model = RegistryAlias
        fields = ("id", "name", "version", "version_id", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project = self.context.get("project")
        if project:
            self.fields["version"].queryset = ModelVersion.objects.filter(project=project)


class ModelMetricSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = ModelMetric
        fields = ("id", "name", "value", "step", "timestamp", "metadata")


class RegistryEventSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = LifecycleEvent
        fields = ("id", "event_type", "from_state", "to_state", "metadata", "created_at")
