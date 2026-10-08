from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth.models import UserAvatar
from apps.auth.services.cookies import clear_refresh_token_cookie, verify_auth_security_headers
from apps.auth.services.otp import (
    check_and_record_otp_cooldown,
    read_token,
    send_otp,
    verify_otp,
)
from apps.auth.services.tokens import create_auth_response, revoke_user_refresh_tokens
from apps.auth.throttles import PasswordResetRateThrottle, RegistrationRateThrottle


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class OTPSerializer(EmailSerializer):
    otp_code = serializers.RegexField(r"^\d{6}$")


class RegistrationOTPRequestEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (RegistrationRateThrottle,)

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": "An account already exists for this email."})
        send_otp(email=email, purpose="registration")
        return Response({"message": "Verification code sent.", "email": email})


class RegistrationOTPVerifyEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (RegistrationRateThrottle,)

    def post(self, request):
        serializer = OTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = verify_otp(
            email=serializer.validated_data["email"].lower(),
            code=serializer.validated_data["otp_code"],
            purpose="registration",
        )
        return Response({"message": "Email verified.", "registration_token": token})


class CompleteRegistrationEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (RegistrationRateThrottle,)

    def post(self, request):
        verify_auth_security_headers(request)
        token = str(request.data.get("registration_token", ""))
        try:
            payload = read_token(token, "registration", consume=False)
        except TypeError:
            payload = read_token(token, "registration")
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=payload["email"]).exists():
            raise serializers.ValidationError({"email": "An account already exists for this email."})

        full_name = str(request.data.get("full_name", ""))
        temp_user = user_model(email=payload["email"], full_name=full_name)
        password = str(request.data.get("password", ""))
        try:
            validate_password(password, user=temp_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        try:
            read_token(token, "registration", consume=True)
        except TypeError:
            pass

        user = user_model.objects.create_user(
            email=payload["email"],
            password=password,
            full_name=full_name,
        )
        avatar = request.FILES.get("avatar")
        if avatar:
            user.avatar = avatar
            user.save(update_fields=["avatar"])
            UserAvatar.objects.create(user=user, image=user.avatar.name)
        return create_auth_response(
            user,
            {"message": "Account created.", "is_new_user": True},
            status=status.HTTP_201_CREATED,
        )


class PasswordResetRequestEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (PasswordResetRateThrottle,)

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        if get_user_model().objects.filter(email__iexact=email, is_active=True).exists():
            send_otp(email=email, purpose="password_reset")
        else:
            check_and_record_otp_cooldown(email=email, purpose="password_reset")
        return Response({"message": "If the account exists, a verification code was sent.", "email": email})


class PasswordResetVerifyEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (PasswordResetRateThrottle,)

    def post(self, request):
        serializer = OTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = verify_otp(
            email=serializer.validated_data["email"].lower(),
            code=serializer.validated_data["otp_code"],
            purpose="password_reset",
        )
        return Response({"message": "Verification code accepted.", "reset_token": token})


class PasswordResetCompleteEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (PasswordResetRateThrottle,)

    def post(self, request):
        token = str(request.data.get("reset_token", ""))
        try:
            payload = read_token(token, "password_reset", consume=False)
        except TypeError:
            payload = read_token(token, "password_reset")
        user_model = get_user_model()
        try:
            user = user_model.objects.get(email__iexact=payload["email"], is_active=True)
        except user_model.DoesNotExist:
            raise serializers.ValidationError({"token": "User account not found or inactive."})

        password = str(request.data.get("new_password", ""))
        try:
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})

        try:
            read_token(token, "password_reset", consume=True)
        except TypeError:
            pass

        user.set_password(password)
        user.save(update_fields=["password"])

        revoke_user_refresh_tokens(user)

        response = Response({"message": "Password reset completed."})
        clear_refresh_token_cookie(response)
        return response
