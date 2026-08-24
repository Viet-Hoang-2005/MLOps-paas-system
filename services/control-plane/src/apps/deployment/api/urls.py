from django.urls import path

from .endpoints import (
    BuildCancelEndpoint,
    BuildDetailEndpoint,
    BuildListCreateEndpoint,
    BuildLogsEndpoint,
    DeploymentDetailEndpoint,
    DeploymentListCreateEndpoint,
    DeploymentLogsEndpoint,
    DeploymentStopEndpoint,
    EndpointListEndpoint,
    EndpointLogsEndpoint,
)

build_patterns = [
    path("", BuildListCreateEndpoint.as_view(), name="build-list"),
    path("<uuid:build_id>/", BuildDetailEndpoint.as_view(), name="build-detail"),
    path("<uuid:build_id>/cancel/", BuildCancelEndpoint.as_view(), name="build-cancel"),
    path("<uuid:build_id>/logs/", BuildLogsEndpoint.as_view(), name="build-logs"),
]
deployment_patterns = [
    path("", DeploymentListCreateEndpoint.as_view(), name="deployment-list"),
    path("<uuid:deployment_id>/", DeploymentDetailEndpoint.as_view(), name="deployment-detail"),
    path("<uuid:deployment_id>/logs/", DeploymentLogsEndpoint.as_view(), name="deployment-logs"),
    path("<uuid:deployment_id>/stop/", DeploymentStopEndpoint.as_view(), name="deployment-stop"),
]
endpoint_patterns = [
    path("", EndpointListEndpoint.as_view(), name="endpoint-list"),
    path("<uuid:endpoint_id>/logs/", EndpointLogsEndpoint.as_view(), name="endpoint-logs"),
]
