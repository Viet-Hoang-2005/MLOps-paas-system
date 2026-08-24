from django.urls import path

from .endpoints import APIKeyDetailEndpoint, APIKeyListCreateEndpoint, APIKeyRegenerateEndpoint

urlpatterns = [
    path("", APIKeyListCreateEndpoint.as_view(), name="api-key-list"),
    path("<uuid:key_id>/", APIKeyDetailEndpoint.as_view(), name="api-key-detail"),
    path("<uuid:key_id>/regenerate/", APIKeyRegenerateEndpoint.as_view(), name="api-key-regenerate"),
]
