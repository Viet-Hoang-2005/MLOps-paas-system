from django.conf import settings
from django.db import DatabaseError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.training.resources.options import CPU_PROFILES, GPU_MODELS, runtime_options
from common.api.exceptions import ServiceUnavailable


class TrainingUsageEndpoint(APIView):
    def get(self, request):
        from apps.training.resources.quota import usage

        try:
            return Response(usage(request.user))
        except DatabaseError as exc:
            raise ServiceUnavailable("Training quota is temporarily unavailable.") from exc


class TrainingRuntimeCapabilitiesEndpoint(APIView):
    def get(self, request):
        if not settings.TRAINING_ENABLED:
            return Response(
                {
                    "enabled": False,
                    "backend": settings.TRAINING_BACKEND,
                    "cpu_profiles": [],
                    "runtime_options_seconds": [],
                    "accelerators": [],
                }
            )
        accelerators = [{"type": "none", "counts": [0]}]
        local_gpu = None
        local_resources = None
        cpu_profiles = [
            {"id": name, "vcpu": cpu, "memory_mb": memory}
            for name, (cpu, memory) in zip(("small", "medium", "large"), CPU_PROFILES, strict=True)
        ]
        if settings.TRAINING_BACKEND == "docker":
            from apps.training.resources.local_capacity import capacity, public_capacity

            snapshot = capacity(force=request.query_params.get("refresh") == "1")
            local_resources = public_capacity(snapshot)
            cpu_profiles = snapshot["cpu_profiles"]
            from apps.training.resources.local_gpu import inventory

            local_gpu = (
                inventory(force=request.query_params.get("refresh") == "1")
                if settings.TRAINING_GPU_ENABLED and 1 in settings.TRAINING_GPU_COUNTS
                else {"status": "disabled", "reason": "gpu_disabled", "devices": []}
            )
        if settings.TRAINING_GPU_ENABLED and 1 in settings.TRAINING_GPU_COUNTS:
            if settings.TRAINING_BACKEND == "argo":
                accelerators.extend({"type": "gpu", "model": model, "counts": [1]} for model in GPU_MODELS)
            elif local_gpu and local_gpu["status"] == "available":
                accelerators.extend(
                    {"type": "gpu", "model": "", "device_id": device["id"], "counts": [1]}
                    for device in local_gpu["devices"]
                )
        return Response(
            {
                "enabled": bool(cpu_profiles),
                "runtime_options_seconds": runtime_options(),
                "dispatch_timeout_seconds": settings.EXECUTION_DISPATCH_TIMEOUT_SECONDS,
                "backend": settings.TRAINING_BACKEND,
                "cpu_profiles": cpu_profiles,
                "accelerators": accelerators,
                **({"local_gpu": local_gpu} if local_gpu is not None else {}),
                **({"local_resources": local_resources} if local_resources is not None else {}),
            }
        )
