from django.contrib.auth import get_user_model
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth.otp.challenges import check_and_record_otp_cooldown, send_otp, verify_otp
from apps.auth.otp.serializers import EmailSerializer, OTPSerializer
from apps.auth.passwords.updates import complete_password_update
from apps.auth.throttles import PasswordResetRateThrottle


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
        return complete_password_update(
            str(request.data.get("reset_token", "")),
            str(request.data.get("new_password", "")),
        )
