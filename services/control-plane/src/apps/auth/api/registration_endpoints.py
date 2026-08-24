from django.contrib.auth import get_user_model
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth.models import UserAvatar
from apps.auth.services.otp import read_token, send_otp, verify_otp
from apps.auth.services.tokens import token_payload


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class OTPSerializer(EmailSerializer):
    otp_code = serializers.RegexField(r"^\d{6}$")


class RegistrationOTPRequestEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

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

    def post(self, request):
        token = str(request.data.get("registration_token", ""))
        payload = read_token(token, "registration")
        password = str(request.data.get("password", ""))
        if len(password) < 8:
            raise serializers.ValidationError({"password": "Password must contain at least 8 characters."})
        user = get_user_model().objects.create_user( # type: ignore[attr-defined]
            email=payload["email"],
            password=password,
            full_name=str(request.data.get("full_name", "")),
        )
        avatar = request.FILES.get("avatar")
        if avatar:
            user.avatar = avatar
            user.save(update_fields=["avatar"])
            UserAvatar.objects.create(user=user, image=user.avatar.name)
        return Response(
            token_payload(user, message="Account created.", is_new_user=True),
            status=status.HTTP_201_CREATED,
        )


class PasswordResetRequestEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        if get_user_model().objects.filter(email__iexact=email, is_active=True).exists():
            send_otp(email=email, purpose="password_reset")
        return Response({"message": "If the account exists, a verification code was sent.", "email": email})


class PasswordResetVerifyEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

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

    def post(self, request):
        payload = read_token(str(request.data.get("reset_token", "")), "password_reset")
        password = str(request.data.get("new_password", ""))
        if len(password) < 8:
            raise serializers.ValidationError({"new_password": "Password must contain at least 8 characters."})
        user = get_user_model().objects.get(email__iexact=payload["email"], is_active=True)
        user.set_password(password)
        user.save(update_fields=["password"])
        return Response({"message": "Password reset completed."})
