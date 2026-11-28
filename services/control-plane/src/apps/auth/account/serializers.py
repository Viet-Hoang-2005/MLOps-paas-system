from django.contrib.auth import get_user_model
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "email",
            "tenant_id",
            "full_name",
            "description",
            "pronouns",
            "company",
            "avatar",
            "field_of_work",
            "country",
            "auth_provider",
            "date_joined",
        )
        read_only_fields = ("email", "tenant_id", "auth_provider", "date_joined", "avatar")
