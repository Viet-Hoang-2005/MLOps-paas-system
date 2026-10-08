from rest_framework import serializers

from apps.catalog.models import ModelPreview, ModelProject, PreviewAsset, WorkspaceAsset
from apps.deployment.services.runtime_health import effective_health
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage


class ModelProjectSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    flavor = serializers.SerializerMethodField()
    lifecycle_status = serializers.SerializerMethodField()
    active_endpoint = serializers.SerializerMethodField()
    source_code = serializers.SerializerMethodField()
    reference_data = serializers.SerializerMethodField()
    latest_version_id = serializers.SerializerMethodField()
    preview_revision = serializers.IntegerField(source="preview.revision", read_only=True)
    preview_changed = serializers.SerializerMethodField()

    class Meta:
        model = ModelProject
        fields = (
            "id",
            "name",
            "description",
            "access_mode",
            "flavor",
            "preview_revision",
            "preview_changed",
            "source_code",
            "reference_data",
            "lifecycle_status",
            "latest_version_id",
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
        queryset = ModelProject.objects.filter(owner=request.user, name=value, is_active=True)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if request and queryset.exists():
            raise Conflict(f"A model project named {value} already exists.")
        return value

    def get_flavor(self, instance):
        return instance.active_deployment.version.flavor if self._has_running(instance) else instance.preview.flavor

    @staticmethod
    def _has_running(instance):
        return bool(instance.active_deployment_id and instance.active_deployment.status == "succeeded")

    def get_preview_changed(self, instance):
        return bool(
            self._has_running(instance)
            and instance.active_deployment.build.preview_revision != instance.preview.revision
        )

    def get_lifecycle_status(self, instance):
        """Return the current user-facing lifecycle state for the management list."""
        if self._has_running(instance):
            return "running"
        return "registered" if instance.versions.exists() else "preview"

    def get_active_endpoint(self, instance):
        """Return only the explicitly selected Running deployment endpoint."""
        for deployment in [instance.active_deployment] if self._has_running(instance) else []:
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
                "version_number": deployment.version.version,
                "url": prediction_url,
                "health_url": health_url,
                "health_status": effective_health(endpoint),
                "deployment_status": deployment.status,
                "registration_status": deployment.build.registration_status,
                "last_checked_at": endpoint.last_checked_at,
            }
        return None

    def get_latest_version_id(self, instance):
        if self._has_running(instance):
            return str(instance.active_deployment.version.public_id)
        latest = instance.versions.order_by("-registered_at", "-id").first()
        return str(latest.public_id) if latest else None

    def _asset_summary(self, instance, kind):
        if not self._has_running(instance):
            return None
        version = instance.active_deployment.version
        artifact = version.artifacts.filter(
            kind={"code": "source_code", "data": "reference_data"}[kind]
        ).first()
        return (
            {
                "name": artifact.name,
                "checksum": artifact.checksum,
                "size_bytes": artifact.size_bytes,
                "content_type": artifact.content_type,
                "download_url": S3Storage().presigned_get(artifact.uri, 900),
            }
            if artifact
            else None
        )

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


class PreviewAssetSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = PreviewAsset
        fields = ("kind", "name", "checksum", "size_bytes", "content_type", "download_url")

    def get_download_url(self, instance):
        return S3Storage().presigned_get(instance.s3_uri, 900)


class ModelPreviewSerializer(serializers.ModelSerializer):
    assets = PreviewAssetSerializer(many=True)

    class Meta:
        model = ModelPreview
        fields = ("revision", "flavor", "artifact_format", "requirements_text", "assets", "updated_at")


class UploadedAssetInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PreviewAsset.KINDS)
    name = serializers.CharField(max_length=255)
    s3_uri = serializers.CharField(max_length=1024)


class PresignedUploadItemSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PreviewAsset.KINDS)
    filename = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField(min_value=1, required=False)
    content_type = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default="application/octet-stream"
    )


class ProjectPreviewUploadUrlsRequestSerializer(serializers.Serializer):
    flavor = serializers.ChoiceField(choices=("sklearn", "xgboost", "pytorch", "tensorflow"), required=False)
    artifact_format = serializers.ChoiceField(choices=("raw", "mlflow_zip"), required=False)
    files = serializers.ListField(child=PresignedUploadItemSerializer(), min_length=1)


class NewProjectUploadUrlsRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    flavor = serializers.ChoiceField(choices=("sklearn", "xgboost", "pytorch", "tensorflow"), required=False)
    artifact_format = serializers.ChoiceField(choices=("raw", "mlflow_zip"), required=False)
    files = serializers.ListField(child=PresignedUploadItemSerializer(), min_length=1)

    def validate_name(self, value):
        request = self.context.get("request")
        if request and ModelProject.objects.filter(owner=request.user, name=value, is_active=True).exists():
            raise Conflict(f"A model project named {value} already exists.")
        return value


class PreviewWriteSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    flavor = serializers.ChoiceField(choices=("sklearn", "xgboost", "pytorch", "tensorflow"), required=False)
    artifact_format = serializers.ChoiceField(choices=("raw", "mlflow_zip"), required=False)
    requirements_text = serializers.CharField(required=False, allow_blank=True)
    remove_assets = serializers.ListField(child=serializers.ChoiceField(choices=PreviewAsset.KINDS), required=False)
    assets = serializers.ListField(child=UploadedAssetInputSerializer(), required=False)

    def validate(self, attrs):
        if any(key.endswith("_file") for key in self.initial_data):
            raise serializers.ValidationError({"assets": "Upload files with a presigned staging URL."})
        return attrs


class ProjectCreateSerializer(PreviewWriteSerializer):
    project_id = serializers.UUIDField(required=False)
    revision = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    access_mode = serializers.ChoiceField(choices=ModelProject.ACCESS_MODES, default="private")
    flavor = serializers.ChoiceField(choices=("sklearn", "xgboost", "pytorch", "tensorflow"))

    def validate_name(self, value):
        request = self.context.get("request")
        if request and ModelProject.objects.filter(owner=request.user, name=value, is_active=True).exists():
            raise Conflict(f"A model project named {value} already exists.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        has_asset = any(asset.get("kind") == "source_artifact" for asset in attrs.get("assets", []))
        if not has_asset:
            raise serializers.ValidationError({"source_artifact": "A model artifact is required."})
        return attrs
