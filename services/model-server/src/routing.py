"""Resolve immutable model metadata to its serving worker."""

import os
from typing import Any

from fastapi import HTTPException

DEEP_LEARNING_FLAVORS = frozenset({"pytorch", "tensorflow"})


def serving_engine_for_flavor(flavor: Any) -> str:
    normalized_flavor = str(flavor or "").strip().lower()
    return "dl" if normalized_flavor in DEEP_LEARNING_FLAVORS else "ml"


def resolve_worker_url(model_record: dict[str, Any], endpoint_path: str) -> str:
    serving_engine = serving_engine_for_flavor(model_record.get("flavor"))
    target_port = 5001 if serving_engine == "ml" else 5002
    container_name = model_record.get("endpoint_container_name")
    deployment_status = model_record.get("deployment_status")
    if not container_name:
        if deployment_status in {"stopped", "failed", "unhealthy"}:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Model deployment is not active (current status: '{deployment_status}'). "
                    "Please deploy the model from the Control Plane first."
                ),
            )
        if os.environ.get("KUBERNETES_SERVICE_HOST"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Model endpoint is not deployed yet. "
                    "Please trigger a deployment from the Control Plane first."
                ),
            )
        fallback = (
            "machine-learning-serving"
            if serving_engine == "ml"
            else "deep-learning-serving"
        )
        return f"http://{fallback}:{target_port}{endpoint_path}"
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        service_name = (
            f"{container_name}-svc"
            if not container_name.endswith("-svc")
            else container_name
        )
        namespace = os.environ.get(
            "MODEL_RUNTIME_NAMESPACE",
            "mlops-model-runtimes",
        ).strip()
        host = f"{service_name}.{namespace}.svc.cluster.local"
    else:
        host = container_name
    return f"http://{host}:{target_port}{endpoint_path}"
