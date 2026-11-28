from rest_framework import serializers

from apps.training.outputs.models import TrainingOutput


class TrainingOutputSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = TrainingOutput
        fields = (
            "id",
            "kind",
            "relative_path",
            "s3_uri",
            "checksum",
            "size_bytes",
            "content_type",
            "metadata",
            "created_at",
        )
