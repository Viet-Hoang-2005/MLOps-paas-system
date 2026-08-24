from rest_framework import serializers

from apps.catalog.artifact_types import ARTIFACT_FORMATS, validate_source_artifact
from apps.deployment.models import Build, BuildInputAsset, Deployment, Endpoint
from apps.registry.models import ModelVersion


class BuildSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    project_id = serializers.UUIDField(source="project.public_id", read_only=True)
    source_job_id = serializers.SerializerMethodField()
    version_id = serializers.UUIDField(source="version.public_id", allow_null=True, read_only=True)
    version_number = serializers.CharField(source="version.version", allow_null=True, read_only=True)
    version = serializers.SlugRelatedField(
        slug_field="public_id", queryset=ModelVersion.objects.none(), required=False, write_only=True
    )
    input_assets = serializers.SerializerMethodField()

    class Meta:
        model = Build
        fields = (
            "id",
            "project_id",
            "source_job_id",
            "version",
            "version_id",
            "version_number",
            "flavor",
            "artifact_format",
            "requirements_snapshot",
            "backend",
            "status",
            "celery_task_id",
            "external_build_id",
            "image_uri",
            "image_digest",
            "package_uri",
            "input_assets",
            "logs",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "backend",
            "status",
            "celery_task_id",
            "external_build_id",
            "image_uri",
            "image_digest",
            "package_uri",
            "logs",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )

    @staticmethod
    def get_source_job_id(instance):
        return instance.source_job_reference or (
            instance.source_job.public_id if instance.source_job_id else None
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["version"].queryset = ModelVersion.objects.filter(project__owner=request.user)

    @staticmethod
    def get_input_assets(instance):
        return BuildInputAssetSerializer(instance.input_assets.all(), many=True).data


class BuildInputAssetSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = BuildInputAsset
        fields = ("id", "kind", "name", "checksum", "size_bytes", "content_type", "purged_at")


class ManualBuildCreateSerializer(serializers.Serializer):
    flavor = serializers.ChoiceField(choices=("sklearn", "xgboost", "pytorch", "tensorflow"))
    artifact_format = serializers.ChoiceField(choices=ARTIFACT_FORMATS, default="raw")
    requirements_text = serializers.CharField(required=False, allow_blank=True, default="")
    source_artifact = serializers.FileField()
    label_mapping_file = serializers.FileField(required=False)
    metrics_file = serializers.FileField(required=False)
    params_file = serializers.FileField(required=False)
    model_insights_file = serializers.FileField(required=False)
    feature_importance_file = serializers.FileField(required=False)
    input_schema_file = serializers.FileField(required=False)

    def validate(self, attrs):
        validate_source_artifact(
            filename=attrs["source_artifact"].name,
            flavor=attrs["flavor"],
            artifact_format=attrs["artifact_format"],
        )
        if attrs["artifact_format"] == "mlflow_zip":
            extras = [field for field in (
                "label_mapping_file", "metrics_file", "params_file", "model_insights_file",
                "feature_importance_file", "input_schema_file",
            ) if attrs.get(field)]
            if extras:
                raise serializers.ValidationError(
                    {field: "Include this file inside the model package ZIP instead." for field in extras}
                )
        return attrs


class DeploymentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    version_id = serializers.UUIDField(source="version.public_id", read_only=True)
    build = serializers.SlugRelatedField(slug_field="public_id", queryset=Build.objects.none(), write_only=True)
    build_id = serializers.UUIDField(source="build.public_id", read_only=True)

    class Meta:
        model = Deployment
        fields = (
            "id",
            "version_id",
            "build",
            "build_id",
            "backend",
            "status",
            "celery_task_id",
            "external_deployment_id",
            "error_message",
            "deployed_at",
            "stopped_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "version_id",
            "backend",
            "status",
            "celery_task_id",
            "external_deployment_id",
            "error_message",
            "deployed_at",
            "stopped_at",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["build"].queryset = Build.objects.filter(
                project__owner=request.user, status="ready", version__isnull=False
            )


class EndpointSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    deployment_id = serializers.UUIDField(source="deployment.public_id", read_only=True)
    version_id = serializers.UUIDField(source="deployment.version.public_id", read_only=True)

    class Meta:
        model = Endpoint
        fields = (
            "id",
            "deployment_id",
            "version_id",
            "public_url",
            "internal_url",
            "runtime_name",
            "runtime_namespace",
            "health_status",
            "last_checked_at",
            "metadata",
            "created_at",
            "updated_at",
        )
