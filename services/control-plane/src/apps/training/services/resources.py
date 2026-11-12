from django.conf import settings
from rest_framework.exceptions import ValidationError

CPU_PROFILES = [(1, 2048), (2, 4096), (4, 8192)]
RUNTIME_OPTIONS = [900, 1800, 3600, 7200, 21600, 43200, 86400]
GPU_MODELS = ("t4", "a10g")


def runtime_options():
    maximum = settings.TRAINING_MAX_RUNTIME_SECONDS
    return sorted({value for value in RUNTIME_OPTIONS if value <= maximum} | {maximum})


def validate_resources(values, instance=None, *, local_capacity=None):
    def value(name, default):
        return values.get(name, getattr(instance, name, default))

    errors = {}
    submitted = instance is not None and instance.status not in {"editing", "pending"}
    if submitted:
        for field in ("vcpu", "memory_mb"):
            if field in values and values[field] != getattr(instance, field):
                errors[field] = "Submitted training resources are immutable."
    choices = CPU_PROFILES
    if settings.TRAINING_BACKEND == "docker" and not submitted:
        from apps.training.services.local_resources import require_capacity
        local_capacity = local_capacity or require_capacity()
        choices = [(item["vcpu"], item["memory_mb"]) for item in local_capacity["cpu_profiles"]]
        if instance is None and "vcpu" not in values and "memory_mb" not in values:
            default = next((item for item in local_capacity["cpu_profiles"] if item["id"] == "medium"), local_capacity["cpu_profiles"][0])
            values["vcpu"], values["memory_mb"] = default["vcpu"], default["memory_mb"]
    if not (submitted and settings.TRAINING_BACKEND == "docker") and (value("vcpu", 2), value("memory_mb", 4096)) not in choices:
        errors["vcpu"] = "Select a supported CPU/memory profile."
        errors["memory_mb"] = "Select a supported CPU/memory profile."
    runtime = value("max_runtime_seconds", 3600)
    invalid_submitted = submitted and ((runtime is None or runtime <= 0) or (instance.backend == "argo" and runtime > 86400))
    if invalid_submitted or ((not submitted or "max_runtime_seconds" in values) and runtime not in runtime_options()):
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
