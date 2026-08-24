from rest_framework import serializers

from apps.access.models import UserAPIKey
from apps.catalog.models import ModelProject


class APIKeySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    allowed_projects = serializers.SlugRelatedField(
        slug_field="public_id", queryset=ModelProject.objects.none(), many=True, allow_empty=False
    )

    class Meta:
        model = UserAPIKey
        fields: tuple[str, ...] = (
            "id",
            "name",
            "description",
            "key_prefix",
            "allowed_projects",
            "created_at",
            "last_used_at",
            "revoked_at",
        )
        read_only_fields = ("key_prefix", "created_at", "last_used_at", "revoked_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["allowed_projects"].child_relation.queryset = ModelProject.objects.filter(
                owner=request.user,
                is_active=True,
            )


class CreatedAPIKeySerializer(APIKeySerializer):
    key = serializers.CharField(read_only=True)

    class Meta(APIKeySerializer.Meta):
        fields = (
            "id",
            "name",
            "description",
            "key_prefix",
            "allowed_projects",
            "created_at",
            "last_used_at",
            "revoked_at",
            "key",
        )
