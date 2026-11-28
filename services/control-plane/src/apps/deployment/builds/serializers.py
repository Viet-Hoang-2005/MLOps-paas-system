from rest_framework import serializers

from apps.deployment.models import Build, BuildInputAsset


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
            "deletion_state",
            "deletion_error",
            "celery_task_id",
            "external_build_id",
            "image_uri",
            "image_digest",
            "package_uri",
            "input_assets",
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
