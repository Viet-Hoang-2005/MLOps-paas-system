from rest_framework import serializers

from apps.catalog.models import ModelPreview, ModelProject, PreviewAsset
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage


class PreviewAssetSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = PreviewAsset
        fields = ("kind", "name", "checksum", "size_bytes", "content_type", "download_url")

    def get_download_url(self, instance):
        return S3Storage().presigned_get(instance.s3_uri, 900, public=True)


class ModelPreviewSerializer(serializers.ModelSerializer):
    assets = PreviewAssetSerializer(many=True)

    class Meta:
        model = ModelPreview
        fields = ("revision", "flavor", "artifact_format", "requirements_text", "assets", "updated_at")


class UploadedAssetInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PreviewAsset.KINDS)
    name = serializers.CharField(max_length=255)
    s3_uri = serializers.CharField(max_length=1024)
    checksum = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class PresignedUploadItemSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PreviewAsset.KINDS)
    filename = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField(min_value=1, required=True)
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
