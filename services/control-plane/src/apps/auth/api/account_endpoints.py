from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth.api.serializers import UserSerializer
from apps.auth.services.avatars import update_profile
from apps.auth.services.cookies import verify_auth_security_headers
from apps.auth.services.otp import send_otp, verify_otp
from apps.auth.services.passwords import complete_password_update
from apps.auth.throttles import PasswordChangeRateThrottle
from apps.observability.services.outbox import enqueue_event


class ProfileEndpoint(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    def put(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        upload = request.FILES.get("avatar")
        if "avatar" in request.data and upload is None:
            raise serializers.ValidationError({"avatar": "Upload an image file."})
        update_profile(
            request.user,
            changes=serializer.validated_data,
            avatar=upload,
            remove=str(request.data.get("remove_avatar", "")).lower() == "true",
        )
        return Response({"message": "Profile updated."})


class AccountDeleteEndpoint(APIView):
    def delete(self, request):
        request.user.soft_delete()
        enqueue_event(
            topic="identity.events",
            aggregate_type="user",
            aggregate_id=request.user.public_id,
            event_type="tenant.disabled",
            payload={"user_id": str(request.user.public_id), "tenant_id": request.user.tenant_id},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeRequestEndpoint(APIView):
    throttle_classes = (PasswordChangeRateThrottle,)

    def post(self, request):
        send_otp(email=request.user.email, purpose="password_change")
        return Response({"message": "Verification code sent."})


class PasswordChangeVerifyEndpoint(APIView):
    throttle_classes = (PasswordChangeRateThrottle,)

    def post(self, request):
        token = verify_otp(
            email=request.user.email,
            code=str(request.data.get("otp_code", "")),
            purpose="password_change",
        )
        return Response({"message": "Verification code accepted.", "password_change_token": token})


class PasswordChangeCompleteEndpoint(APIView):
    def post(self, request):
        if request.headers.get("Origin") or request.headers.get("X-Requested-With"):
            verify_auth_security_headers(request)

        return complete_password_update(
            str(request.data.get("password_change_token", "")),
            str(request.data.get("new_password", "")),
            actor=request.user,
        )
