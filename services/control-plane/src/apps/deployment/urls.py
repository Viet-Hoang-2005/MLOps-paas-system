from django.urls import path

from apps.deployment.builds.api import (
    BuildCancelEndpoint,
    BuildDetailEndpoint,
    BuildLogsEndpoint,
    BuildRebuildEndpoint,
    BuildRegisterEndpoint,
)
from apps.deployment.serving.api import (
    DeploymentDetailEndpoint,
    DeploymentListCreateEndpoint,
    DeploymentLogsEndpoint,
    DeploymentRuntimeLogsEndpoint,
    DeploymentStopEndpoint,
)

build_patterns = [
    path("<uuid:build_id>/", BuildDetailEndpoint.as_view(), name="build-detail"),
    path("<uuid:build_id>/cancel/", BuildCancelEndpoint.as_view(), name="build-cancel"),
    path("<uuid:build_id>/logs/", BuildLogsEndpoint.as_view(), name="build-logs"),
    path("<uuid:build_id>/register/", BuildRegisterEndpoint.as_view(), name="build-register"),
    path("<uuid:build_id>/rebuild/", BuildRebuildEndpoint.as_view(), name="build-rebuild"),
]
deployment_patterns = [
    path("", DeploymentListCreateEndpoint.as_view(), name="deployment-list"),
    path("<uuid:deployment_id>/", DeploymentDetailEndpoint.as_view(), name="deployment-detail"),
    path("<uuid:deployment_id>/logs/", DeploymentLogsEndpoint.as_view(), name="deployment-logs"),
    path("<uuid:deployment_id>/runtime-logs/", DeploymentRuntimeLogsEndpoint.as_view(), name="deployment-runtime-logs"),
    path("<uuid:deployment_id>/stop/", DeploymentStopEndpoint.as_view(), name="deployment-stop"),
]
