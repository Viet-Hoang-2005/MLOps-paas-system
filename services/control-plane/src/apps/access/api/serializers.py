from rest_framework import serializers

from apps.access.models import UserAPIKey
from apps.catalog.models import ModelProject
from common.api.exceptions import Conflict


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

    def validate_name(self, value):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return value
        qs = UserAPIKey.objects.filter(user=request.user, name=value, revoked_at__isnull=True)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict("An active API key with this name already exists.")
        return value


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
