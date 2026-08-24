import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import RegistrationSerializer, TenantTokenSerializer


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


token_endpoint = TokenObtainPairView.as_view(serializer_class=TenantTokenSerializer)
refresh_endpoint = TokenRefreshView.as_view()
