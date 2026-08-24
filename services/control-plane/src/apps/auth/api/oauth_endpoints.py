from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth.services.oauth import authenticate_github, authenticate_google
from apps.auth.services.tokens import token_payload


class GoogleOAuthEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        token = str(request.data.get("token", ""))
        if not token:
            raise serializers.ValidationError({"token": "Google access token is required."})
        user, created = authenticate_google(token)
        return Response(token_payload(user, message="Signed in with Google.", is_new_user=created))


class GitHubOAuthEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        code = str(request.data.get("code", ""))
        if not code:
            raise serializers.ValidationError({"code": "GitHub authorization code is required."})
        user, created = authenticate_github(code, str(request.data.get("redirect_uri", "")))
        return Response(token_payload(user, message="Signed in with GitHub.", is_new_user=created))
