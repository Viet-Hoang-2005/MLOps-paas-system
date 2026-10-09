"""Resolve immutable model metadata to its serving worker."""

import os
from typing import Any

from fastapi import HTTPException

DEEP_LEARNING_FLAVORS = frozenset({"pytorch", "tensorflow", "keras"})


def serving_engine_for_flavor(flavor: Any) -> str:
    normalized_flavor = str(flavor or "").strip().lower()
    return "dl" if normalized_flavor in DEEP_LEARNING_FLAVORS else "ml"


def resolve_worker_url(model_record: dict[str, Any], endpoint_path: str) -> str:
    serving_engine = serving_engine_for_flavor(model_record.get("flavor"))
    target_port = 5001 if serving_engine == "ml" else 5002
    container_name = model_record.get("endpoint_container_name")
    deployment_status = model_record.get("deployment_status")
    if deployment_status != "succeeded" or not container_name:
        raise HTTPException(
            status_code=409,
            detail="Model has no active succeeded deployment. Deploy the model from the Control Plane first.",
        )
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        service_name = f"{container_name}-svc" if not container_name.endswith("-svc") else container_name
        namespace = os.environ.get(
            "MODEL_RUNTIME_NAMESPACE",
            "mlops-model-runtimes",
        ).strip()
        host = f"{service_name}.{namespace}.svc.cluster.local"
    else:
        host = container_name
    return f"http://{host}:{target_port}{endpoint_path}"


def build_worker_payload(model_record: dict[str, Any], features: dict[str, Any], model_version_id: str) -> dict[str, Any]:
    """Body for the worker's /predict: BentoML (deep learning) wraps arguments by name."""
    body = {"features": features, "model_version_id": model_version_id}
    if serving_engine_for_flavor(model_record.get("flavor")) == "dl":
        return {"payload": body}
    return body
