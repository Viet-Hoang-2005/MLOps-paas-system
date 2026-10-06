from typing import cast

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.utils import datetime_from_epoch

from apps.auth.models import CustomUser, UserAvatar


class _KeyIdTokenMixin:
    def __str__(self):
        backend = self.get_token_backend()
        payload = self.payload.copy()
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


class TenantTokenRefreshSerializer(TokenRefreshSerializer):
    # The model gateway resolves the verifying key by `kid`, so refreshed tokens need it too.
    token_class = _KeyIdRefreshToken

    def validate(self, attrs):
        refresh_token = self.token_class(attrs["refresh"])
        tenant_id = refresh_token.payload.get("tenant_id", "")
        data = super().validate(attrs)
        data["tenant_id"] = tenant_id

        if "refresh" in data and "rest_framework_simplejwt.token_blacklist" in settings.INSTALLED_APPS:
            new_token = self.token_class(data["refresh"])
            user_id = new_token.payload.get(api_settings.USER_ID_CLAIM)
            user_model = get_user_model()
            try:
                user = user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
            except user_model.DoesNotExist:
                user = None
            OutstandingToken.objects.create(
                user=user,
                jti=new_token.payload[api_settings.JTI_CLAIM],
                token=str(new_token),
                created_at=datetime_from_epoch(new_token.payload["iat"]),
                expires_at=datetime_from_epoch(new_token.payload["exp"]),
            )
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
    password = serializers.CharField(write_only=True)

    class Meta:
        model = get_user_model()
        fields = ("email", "password", "full_name")

    def validate_password(self, value):
        user = get_user_model()(
            email=self.initial_data.get("email", ""),
            full_name=self.initial_data.get("full_name", ""),
        )
        try:
            validate_password(value, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def create(self, validated_data):
        return get_user_model().objects.create_user(**validated_data)


class AvatarSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = UserAvatar
        fields = ("id", "image", "created_at")
