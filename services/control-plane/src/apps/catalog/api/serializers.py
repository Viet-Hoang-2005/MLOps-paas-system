from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from rest_framework import serializers

from apps.catalog.models import ModelProject, WorkspaceAsset


class ModelProjectSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    flavor = serializers.SerializerMethodField()
    lifecycle_status = serializers.SerializerMethodField()
    active_endpoint = serializers.SerializerMethodField()
    source_code = serializers.SerializerMethodField()
    reference_data = serializers.SerializerMethodField()

    class Meta:
        model = ModelProject
        fields = (
            "id",
            "name",
            "description",
            "access_mode",
            "flavor",
            "source_code",
            "reference_data",
            "lifecycle_status",
            "active_endpoint",
            "is_active",
            "deletion_state",
            "deletion_error",
            "deletion_task_id",
            "deleted_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "is_active",
            "deletion_state",
            "deletion_error",
            "deletion_task_id",
            "deleted_at",
            "created_at",
            "updated_at",
        )

    def validate_name(self, value):
        request = self.context.get("request")
        queryset = ModelProject.objects.filter(owner=request.user, name=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if request and queryset.exists():
            raise Conflict(f"A model project named {value} already exists.")
        return value

    def get_flavor(self, instance):
        version = instance.versions.order_by("-registered_at").first()
        return version.flavor if version else ""

    def get_lifecycle_status(self, instance):
        """Return the current user-facing lifecycle state for the management list."""
        if instance.versions.filter(
            deployments__status__in={"pending", "deploying", "healthy", "unhealthy"}
        ).exists():
            return "deployed"
        if instance.builds.filter(status="ready").exists():
            return "image_ready"
        return "metadata"

    def get_active_endpoint(self, instance):
        """Return the newest non-terminal deployment endpoint for this project."""
        deployments = (
            deployment
            for version in instance.versions.all()
            for deployment in version.deployments.all()
            if deployment.status not in {"failed", "stopped"}
        )
        for deployment in sorted(deployments, key=lambda item: item.created_at, reverse=True):
            endpoint = getattr(deployment, "endpoint", None)
            if endpoint is None:
                continue
            endpoint_base_url = endpoint.public_url.rstrip("/")
            if endpoint_base_url.endswith("/predict"):
                prediction_url = endpoint_base_url
                health_url = f"{endpoint_base_url.removesuffix('/predict')}/health"
            else:
                prediction_url = f"{endpoint_base_url}/predict"
                health_url = f"{endpoint_base_url}/health"
            return {
                "id": str(endpoint.public_id),
                "deployment_id": str(deployment.public_id),
                "version_id": str(deployment.version.public_id),
                "url": prediction_url,
                "health_url": health_url,
                "health_status": endpoint.health_status,
                "deployment_status": deployment.status,
                "last_checked_at": endpoint.last_checked_at,
            }
        return None

    def _asset_summary(self, instance, kind):
        asset = instance.workspace_assets.filter(kind=kind).order_by("-updated_at").first()
        return ProjectAssetSummarySerializer(asset).data if asset else None

    def get_source_code(self, instance):
        return self._asset_summary(instance, "code")

    def get_reference_data(self, instance):
        return self._asset_summary(instance, "data")


class WorkspaceAssetSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = WorkspaceAsset
        fields = (
            "id",
            "kind",
            "relative_path",
            "s3_uri",
            "download_url",
            "checksum",
            "size_bytes",
            "content_type",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("kind", "s3_uri", "checksum", "size_bytes", "content_type", "created_at", "updated_at")

    def get_download_url(self, instance):
        return S3Storage().presigned_get(instance.s3_uri, 900)


class WorkspaceUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    relative_path = serializers.CharField(max_length=512)


class ProjectAssetSummarySerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="relative_path", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = WorkspaceAsset
        fields = ("name", "download_url", "checksum", "size_bytes", "content_type")

    def get_download_url(self, instance):
        return S3Storage().presigned_get(instance.s3_uri, 900)


class ProjectMetadataWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    access_mode = serializers.ChoiceField(choices=ModelProject.ACCESS_MODES, default="private")
    source_code_file = serializers.FileField(required=False)
    reference_data_file = serializers.FileField(required=False)
