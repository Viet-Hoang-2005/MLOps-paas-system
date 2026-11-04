from django.conf import settings
from rest_framework.exceptions import ValidationError

CPU_PROFILES = [(1, 2048), (2, 4096), (4, 8192)]
RUNTIME_OPTIONS = [900, 1800, 3600, 7200, 21600, 43200]
GPU_MODELS = ("t4", "a10g")


def validate_resources(values, instance=None):
    def value(name, default):
        return values.get(name, getattr(instance, name, default))

    errors = {}
    if (value("vcpu", 2), value("memory_mb", 4096)) not in CPU_PROFILES:
        errors["vcpu"] = "Select a supported CPU/memory profile."
        errors["memory_mb"] = "Select a supported CPU/memory profile."
    if value("max_runtime_seconds", 3600) not in RUNTIME_OPTIONS:
        errors["max_runtime_seconds"] = "Select a supported maximum runtime."
    kind, count = value("accelerator_type", "none"), value("accelerator_count", 0)
    model = value("accelerator_model", "")
    local_gpu_id = value("local_gpu_id", "")
    if kind not in {"none", "gpu"}:
        errors["accelerator_type"] = "Select a supported accelerator."
    if kind == "none":
        if count != 0:
            errors["accelerator_count"] = "CPU training requires accelerator_count=0."
        if model:
            errors["accelerator_model"] = "CPU training cannot select a GPU model."
        if local_gpu_id:
            errors["local_gpu_id"] = "CPU training cannot select a GPU."
    elif kind == "gpu":
        if not settings.TRAINING_GPU_ENABLED or count != 1 or 1 not in settings.TRAINING_GPU_COUNTS:
            errors["accelerator_count"] = "Only one enabled GPU is supported."
        if settings.TRAINING_BACKEND == "argo" and model not in GPU_MODELS:
            errors["accelerator_model"] = "Select a supported GPU model."
        if settings.TRAINING_BACKEND == "argo" and local_gpu_id:
            errors["local_gpu_id"] = "Production training cannot select a local GPU."
        if settings.TRAINING_BACKEND == "docker" and model:
            errors["accelerator_model"] = "Local GPU training does not select a GPU model."
        if settings.TRAINING_BACKEND == "docker":
            from apps.training.services.local_gpu import GPU_UUID
            if not GPU_UUID.fullmatch(local_gpu_id or ""):
                errors["local_gpu_id"] = (
                    "This GPU job has no selected device; create a new training job."
                    if instance and not local_gpu_id else "Select an available NVIDIA GPU."
                )
    if errors:
        raise ValidationError(errors)
    return values
