from django.conf import settings
from rest_framework.exceptions import ValidationError

CPU_PROFILES = [(1, 2048), (2, 4096), (4, 8192)]
RUNTIME_OPTIONS = [900, 1800, 3600, 7200, 21600, 43200]


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
    if kind not in {"none", "gpu"}:
        errors["accelerator_type"] = "Select a supported accelerator."
    if kind == "none" and count != 0:
        errors["accelerator_count"] = "CPU training requires accelerator_count=0."
    elif kind == "gpu" and (not settings.TRAINING_GPU_ENABLED or count not in settings.TRAINING_GPU_COUNTS):
        errors["accelerator_count"] = "This GPU configuration is unavailable."
    if errors:
        raise ValidationError(errors)
    return values
