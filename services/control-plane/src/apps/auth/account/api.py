from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth.account.avatars import update_profile
from apps.auth.account.lifecycle import deactivate_user_account
from apps.auth.account.serializers import UserSerializer
from apps.auth.sessions.cookies import clear_refresh_token_cookie


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
        deactivate_user_account(request.user)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_token_cookie(response)
        return response
