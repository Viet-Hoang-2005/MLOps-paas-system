from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth.api.serializers import AvatarSerializer, UserSerializer
from apps.auth.models import UserAvatar
from apps.auth.services.otp import read_token, send_otp, verify_otp
from apps.observability.services.outbox import enqueue_event


class ProfileEndpoint(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    def put(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if str(request.data.get("remove_avatar", "")).lower() == "true":
            user.avatar = None
            user.save(update_fields=["avatar"])
        elif request.FILES.get("avatar"):
            user.avatar = request.FILES["avatar"]
            user.save(update_fields=["avatar"])
            UserAvatar.objects.create(user=user, image=user.avatar.name)
        return Response({"message": "Profile updated."})


class AvatarHistoryEndpoint(APIView):
    def get(self, request):
        current = request.user.avatar.name if request.user.avatar else ""
        avatars = AvatarSerializer(request.user.avatar_history.all(), many=True, context={"request": request}).data
        return Response(
            {
                "avatars": [
                    {
                        "id": item["id"],
                        "url": item["image"],
                        "is_current": bool(current and str(item["image"]).endswith(current)),
                        "created_at": item["created_at"],
                    }
                    for item in avatars
                ]
            }
        )


class AvatarSelectEndpoint(APIView):
    def post(self, request, avatar_id):
        avatar = request.user.avatar_history.get(public_id=avatar_id)
        request.user.avatar = avatar.image.name
        request.user.save(update_fields=["avatar"])
        return Response({"message": "Avatar selected."})


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
    def post(self, request):
        send_otp(email=request.user.email, purpose="password_change")
        return Response({"message": "Verification code sent."})


class PasswordChangeVerifyEndpoint(APIView):
    def post(self, request):
        token = verify_otp(
            email=request.user.email,
            code=str(request.data.get("otp_code", "")),
            purpose="password_change",
        )
        return Response({"message": "Verification code accepted.", "password_change_token": token})


class PasswordChangeCompleteEndpoint(APIView):
    def post(self, request):
        payload = read_token(str(request.data.get("password_change_token", "")), "password_change")
        if payload["email"].lower() != request.user.email.lower():
            raise serializers.ValidationError({"token": "Token belongs to another account."})
        password = str(request.data.get("new_password", ""))
        if len(password) < 8:
            raise serializers.ValidationError({"new_password": "Password must contain at least 8 characters."})
        request.user.set_password(password)
        request.user.save(update_fields=["password"])
        return Response({"message": "Password changed."})
