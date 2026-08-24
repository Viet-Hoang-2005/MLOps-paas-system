from django.conf import settings

from .argo_backends import ArgoBuildBackend, ArgoDeploymentBackend, ArgoDriftBackend, ArgoTrainingBackend
from .docker_backends import DockerBuildBackend, DockerDeploymentBackend, DockerDriftBackend, DockerTrainingBackend


def build_backend(name=None):
    return ArgoBuildBackend() if (name or settings.BUILD_BACKEND) == "argo" else DockerBuildBackend()


def training_backend(name=None):
    return (
        ArgoTrainingBackend()
        if (name or settings.TRAINING_BACKEND) in {"argo", "kubeflow"}
        else DockerTrainingBackend()
    )


def drift_backend(name=None):
    return ArgoDriftBackend() if (name or settings.DRIFT_BACKEND) == "argo" else DockerDriftBackend()


def deployment_backend(name=None):
    return ArgoDeploymentBackend() if (name or settings.DEPLOYMENT_BACKEND) == "argo" else DockerDeploymentBackend()
