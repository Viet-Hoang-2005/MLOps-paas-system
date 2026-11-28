from rest_framework import serializers

from apps.deployment.models import Build, Deployment


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
