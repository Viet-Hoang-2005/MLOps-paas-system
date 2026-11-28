from rest_framework import serializers

from apps.deployment.models import Build, Deployment, Endpoint


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
    health_status = serializers.SerializerMethodField()
    id = serializers.UUIDField(source="public_id", read_only=True)
    deployment_id = serializers.UUIDField(source="deployment.public_id", read_only=True)
    version_id = serializers.UUIDField(source="deployment.version.public_id", read_only=True)

    def get_health_status(self, endpoint):
        from apps.deployment.serving.health import effective_health

        return effective_health(endpoint)

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
