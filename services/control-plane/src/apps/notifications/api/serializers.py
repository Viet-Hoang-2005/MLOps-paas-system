from rest_framework import serializers
from ..models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "type",
            "level",
            "title",
            "message",
            "link",
            "metadata",
            "is_read",
            "created_at",
            "read_at",
        )
        read_only_fields = fields


class UnreadCountSerializer(serializers.Serializer):
    unread_count = serializers.IntegerField()
