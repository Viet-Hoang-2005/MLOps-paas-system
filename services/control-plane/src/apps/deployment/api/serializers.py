from rest_framework import serializers

from apps.deployment.models import Build, BuildInputAsset, Deployment, Endpoint
from apps.registry.models import ModelVersion


class BuildSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    project_id = serializers.UUIDField(source="project.public_id", read_only=True)
    source_job_id = serializers.SerializerMethodField()
    source_kind = serializers.SerializerMethodField()
    source_draft_revision_id = serializers.UUIDField(source="source_draft_revision.public_id", allow_null=True, read_only=True)
    source_version_id = serializers.UUIDField(source="source_version.public_id", allow_null=True, read_only=True)
    version_id = serializers.UUIDField(source="version.public_id", allow_null=True, read_only=True)
    version_number = serializers.CharField(source="version.version", allow_null=True, read_only=True)
    input_assets = serializers.SerializerMethodField()

    class Meta:
        model = Build
        fields = (
            "id",
            "project_id",
            "source_job_id",
            "source_kind",
            "source_draft_revision_id",
            "source_version_id",
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
        return instance.source_job_reference or (instance.source_job.public_id if instance.source_job_id else None)

    @staticmethod
    def get_source_kind(instance):
        return instance.source_kind

    @staticmethod
    def get_input_assets(instance):
        return BuildInputAssetSerializer(instance.input_assets.all(), many=True).data


class BuildInputAssetSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = BuildInputAsset
        fields = ("id", "kind", "name", "checksum", "size_bytes", "content_type", "purged_at")


class DeploymentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    version_id = serializers.UUIDField(source="version.public_id", read_only=True)
    project_id = serializers.UUIDField(source="project.public_id", read_only=True)
    version = serializers.SlugRelatedField(slug_field="public_id", queryset=ModelVersion.objects.none(), write_only=True)
    build_id = serializers.UUIDField(source="build.public_id", read_only=True, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["version"].queryset = ModelVersion.objects.filter(project__owner=request.user)

    class Meta:
        model = Deployment
        fields = (
            "id",
            "project_id",
            "version",
            "version_id",
            "build_id",
            "target",
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
            "project_id",
            "version_id",
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
