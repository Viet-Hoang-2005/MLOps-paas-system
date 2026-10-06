import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from rest_framework import exceptions, generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.auth.api.serializers import (
    RegistrationSerializer,
    TenantTokenRefreshSerializer,
    TenantTokenSerializer,
    _KeyIdRefreshToken,
)
from apps.auth.services.cookies import (
    clear_refresh_token_cookie,
    get_refresh_token_from_request,
    set_refresh_token_cookie,
    verify_auth_security_headers,
)


class RegisterEndpoint(generics.CreateAPIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegistrationSerializer


def _b64(value):
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class JWKSEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        from django.conf import settings

        if settings.JWT_ALGORITHM != "RS256" or not settings.JWT_PUBLIC_KEY:
            return Response({"keys": []})
        key = serialization.load_pem_public_key(settings.JWT_PUBLIC_KEY.encode())
        if not isinstance(key, RSAPublicKey):
            return Response({"keys": []})
        numbers = key.public_numbers()
        return Response(
            {
                "keys": [
                    {
                        "kty": "RSA",
                        "alg": "RS256",
                        "use": "sig",
                        "kid": "mlops-paas-key-1",
                        "n": _b64(numbers.n),
                        "e": _b64(numbers.e),
                    }
                ]
            }
        )


class CookieTokenObtainPairView(TokenObtainPairView):
    serializer_class = TenantTokenSerializer

    def post(self, request, *args, **kwargs):
        verify_auth_security_headers(request)
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            refresh_token = response.data.pop("refresh", None)
            if refresh_token:
                set_refresh_token_cookie(response, refresh_token)
        return response


class CookieTokenRefreshView(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        verify_auth_security_headers(request)
        refresh_token = get_refresh_token_from_request(request)
        if not refresh_token:
            raise exceptions.AuthenticationFailed("Refresh token cookie is missing.")

        serializer = TenantTokenRefreshSerializer(data={"refresh": refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc

        data = dict(serializer.validated_data)
        new_refresh = data.pop("refresh", None)
        response = Response(data, status=status.HTTP_200_OK)
        if new_refresh:
            set_refresh_token_cookie(response, new_refresh)
        return response


class LogoutEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        verify_auth_security_headers(request)
        refresh_token = get_refresh_token_from_request(request)
        if refresh_token:
            try:
                token = _KeyIdRefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                # Expired or malformed tokens are already unusable; still clear the cookie.
                pass
        response = Response({"message": "Successfully logged out."})
        clear_refresh_token_cookie(response)
        return response


token_endpoint = CookieTokenObtainPairView.as_view()
refresh_endpoint = CookieTokenRefreshView.as_view()
logout_endpoint = LogoutEndpoint.as_view()
