from rest_framework import permissions, serializers
from rest_framework.views import APIView

from apps.auth.services.oauth import authenticate_github, authenticate_google
from apps.auth.services.cookies import verify_auth_security_headers
from apps.auth.services.tokens import create_auth_response


class GoogleOAuthEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        verify_auth_security_headers(request)
        token = str(request.data.get("token", ""))
        if not token:
            raise serializers.ValidationError({"token": "Google access token is required."})
        user, created = authenticate_google(token)
        return create_auth_response(user, {"message": "Signed in with Google.", "is_new_user": created})


class GitHubOAuthEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        verify_auth_security_headers(request)
        code = str(request.data.get("code", ""))
        if not code:
            raise serializers.ValidationError({"code": "GitHub authorization code is required."})
        user, created = authenticate_github(code, str(request.data.get("redirect_uri", "")))
        return create_auth_response(user, {"message": "Signed in with GitHub.", "is_new_user": created})
