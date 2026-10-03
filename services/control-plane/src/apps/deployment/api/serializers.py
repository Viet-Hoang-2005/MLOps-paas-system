from rest_framework import serializers

from apps.deployment.models import Build, BuildInputAsset, Deployment, Endpoint


class BuildSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    project_id = serializers.UUIDField(source="project.public_id", read_only=True)
    source_job_id = serializers.SerializerMethodField()
    version_id = serializers.UUIDField(source="version.public_id", allow_null=True, read_only=True)
    version_number = serializers.CharField(source="version.version", allow_null=True, read_only=True)
    input_assets = serializers.SerializerMethodField()

    class Meta:
        model = Build
        fields = (
            "id",
            "project_id",
            "source_job_id",
            "version_id",
            "version_number",
            "flavor",
            "artifact_format",
            "requirements_snapshot",
            "backend",
            "status",
            "preview_revision",
            "registration_status",
            "registration_error",
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
