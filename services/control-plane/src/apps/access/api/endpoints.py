from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.models import UserAPIKey
from apps.access.selectors import active_api_keys

from .serializers import APIKeySerializer, CreatedAPIKeySerializer


class APIKeyListCreateEndpoint(generics.ListCreateAPIView):
    serializer_class = APIKeySerializer

    def get_queryset(self):
        return active_api_keys(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        projects = serializer.validated_data.pop("allowed_projects", [])
        raw, prefix, digest = UserAPIKey.issue()
        api_key = UserAPIKey.objects.create(
            user=request.user, key_prefix=prefix, key_hash=digest, **serializer.validated_data
        )
        api_key.allowed_projects.set(projects)
        payload = CreatedAPIKeySerializer(api_key, context=self.get_serializer_context()).data
        payload["key"] = raw
        return Response(payload, status=status.HTTP_201_CREATED)


class APIKeyDetailEndpoint(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "public_id"
    lookup_url_kwarg = "key_id"
    serializer_class = APIKeySerializer

    def get_queryset(self):
        return UserAPIKey.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        instance.revoked_at = timezone.now()
        instance.save(update_fields=["revoked_at"])


class APIKeyRegenerateEndpoint(APIView):
    def post(self, request, key_id):
        api_key = UserAPIKey.objects.get(user=request.user, public_id=key_id, revoked_at__isnull=True)
        raw, prefix, digest = UserAPIKey.issue()
        api_key.key_prefix = prefix
        api_key.key_hash = digest
        api_key.save(update_fields=["key_prefix", "key_hash"])
        payload = CreatedAPIKeySerializer(api_key, context={"request": request}).data
        payload["key"] = raw
        return Response(payload)
