from typing import cast

import jwt
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.auth.models import CustomUser, UserAvatar


class _KeyIdTokenMixin:
    def __str__(self):
        backend = self.get_token_backend()  # type: ignore[attr-defined]
        payload = self.payload.copy()  # type: ignore[attr-defined]
        if backend.audience is not None:
            payload["aud"] = backend.audience
        if backend.issuer is not None:
            payload["iss"] = backend.issuer
        encoded = jwt.encode(
            payload,
            backend.signing_key,
            algorithm=backend.algorithm,
            headers={"kid": "mlops-paas-key-1"},
            json_encoder=backend.json_encoder,
        )
        return encoded


class _KeyIdAccessToken(_KeyIdTokenMixin, AccessToken):
    pass


class _KeyIdRefreshToken(_KeyIdTokenMixin, RefreshToken):
    access_token_class = _KeyIdAccessToken


class TenantTokenSerializer(TokenObtainPairSerializer):
    token_class = _KeyIdRefreshToken

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["tenant_id"] = user.tenant_id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["tenant_id"] = cast(CustomUser, self.user).tenant_id
        return data


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
        read_only_fields = ("email", "tenant_id", "date_joined")


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = get_user_model()
        fields = ("email", "password", "full_name")

    def create(self, validated_data):
        return get_user_model().objects.create_user(**validated_data) # type: ignore[attr-defined]


class AvatarSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = UserAvatar
        fields = ("id", "image", "created_at")
