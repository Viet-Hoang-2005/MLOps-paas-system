from rest_framework import serializers

from apps.catalog.models import ModelProject
from common.api.exceptions import Conflict


class ModelProjectSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    flavor = serializers.SerializerMethodField()
    active_endpoint = serializers.SerializerMethodField()
    workflow_status = serializers.SerializerMethodField()

    class Meta:
        model = ModelProject
        fields = (
            "id",
            "name",
            "description",
            "access_mode",
            "task_domain",
            "flavor",
            "workflow_status",
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

    def get_workflow_status(self, instance):
        from apps.registry.models import RegistryAlias
        draft = getattr(instance, "draft", None)
        if draft and draft.can_build():
            pass
        elif not instance.versions.exists():
            return "setup"
        if RegistryAlias.objects.filter(project=instance, name="production", version__deployments__status="healthy",
                                        version__deployments__endpoint__health_status="healthy").exists():
            return "deployed"
        return "image_ready" if instance.versions.filter(artifacts__kind="image").exists() else "setup"


class ProjectMetadataWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    access_mode = serializers.ChoiceField(choices=ModelProject.ACCESS_MODES, required=False)
    task_domain = serializers.ChoiceField(choices=ModelProject.TASK_DOMAINS, required=False)


class DraftAssetSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    kind = serializers.CharField()
    name = serializers.CharField()
    download_url = serializers.SerializerMethodField()
    checksum = serializers.CharField(allow_blank=True)
    size_bytes = serializers.IntegerField()
    content_type = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    @staticmethod
    def get_download_url(instance):
        from infrastructure.storage import S3Storage
        return S3Storage().presigned_get(instance.s3_uri, 900)


class ModelDraftSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    flavor = serializers.CharField(allow_blank=True)
    artifact_format = serializers.CharField()
    requirements_snapshot = serializers.CharField(allow_blank=True)
    revision = serializers.IntegerField()
    saved_revision = serializers.IntegerField()
    status = serializers.CharField()
    locked_by_build_id = serializers.SerializerMethodField()
    saved_at = serializers.DateTimeField(allow_null=True)
    saved_snapshot_id = serializers.UUIDField(source="saved_snapshot.public_id", allow_null=True)
    is_dirty = serializers.BooleanField()
    has_mandatory_assets = serializers.SerializerMethodField()
    can_build = serializers.SerializerMethodField()
    assets = DraftAssetSerializer(many=True, read_only=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_locked_by_build_id(self, instance):
        return str(instance.locked_by_build.public_id) if instance.locked_by_build else None

    def get_has_mandatory_assets(self, instance):
        if hasattr(instance, "has_mandatory_assets"):
            is_callable = callable(instance.has_mandatory_assets)
            return instance.has_mandatory_assets() if is_callable else instance.has_mandatory_assets
        return False

    def get_can_build(self, instance):
        if hasattr(instance, "can_build"):
            return instance.can_build() if callable(instance.can_build) else instance.can_build
        return False


class ModelDraftUpdateSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=0)
    flavor = serializers.CharField(max_length=80, required=False, allow_blank=True)
    artifact_format = serializers.ChoiceField(choices=["raw", "archive"], required=False)
    requirements_snapshot = serializers.CharField(required=False, allow_blank=True)


class DraftSaveSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=0)


class DraftAssetUploadUrlSerializer(serializers.Serializer):
    kind = serializers.CharField(max_length=40)
    filename = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField(min_value=0, required=False, default=0)
    checksum = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    content_type = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default="application/octet-stream"
    )


class DraftAssetCompleteSerializer(serializers.Serializer):
    upload_id = serializers.UUIDField()


class DraftBuildSerializer(serializers.Serializer):
    backend = serializers.CharField(max_length=30, required=False, default="docker")


class DraftLoadVersionSerializer(serializers.Serializer):
    version_id = serializers.UUIDField()
    confirm = serializers.BooleanField(required=False, default=False)
