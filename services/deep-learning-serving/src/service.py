"""BentoML adapter and worker lifecycle."""

import os
from typing import Any

import bentoml
import mlflow.pyfunc

from src.inference import run_inference
from src.loading import download_model_artifact, resolve_mlflow_model_dir
from src.logging_utils import (
    RequestLoggingMiddleware,
    configure,
    current_context,
    get_logger,
    log_event,
)

logger = get_logger(__name__)


def _keep_bentoml_operational_log(record):
    return not (
        record.msg == "Exception on %s [%s]"
        and current_context().get("request_id")
    )


def load_runtime_model(model_version_id: str, model_uri: str | None):
    model_dir = "/app/model_artifact"
    if model_uri:
        source_dir = download_model_artifact(model_version_id, model_uri)
        model_dir = str(resolve_mlflow_model_dir(source_dir))
    elif not os.path.exists(model_dir):
        model_dir = "."
    log_event(logger, "INFO", "model_load_started", "Loading deep learning model")
    return mlflow.pyfunc.load_model(model_dir)


@bentoml.service(
    resources={"cpu": "2"},
    traffic={"timeout": 60},
    logging={"access": {"enabled": False}},
)
class DeepLearningModelService:
    def __init__(self):
        configure("deep-learning-serving")
        get_logger("bentoml._internal.server.http_app").addFilter(
            _keep_bentoml_operational_log
        )
        model_version_id = os.environ.get("MODEL_VERSION_ID")
        resolved_id = (
            model_version_id
            if model_version_id and model_version_id != "unknown"
            else "unknown"
        )
        try:
            self.model = load_runtime_model(resolved_id, os.environ.get("MODEL_URI"))
            log_event(logger, "INFO", "model_loaded", "Deep learning model loaded")
        except Exception as exc:
            log_event(
                logger,
                "ERROR",
                "model_load_failed",
                "Deep learning model load failed",
                error_type=type(exc).__name__,
            )
            self.model = None

    @bentoml.api(route="/predict", batchable=False)
    def predict(self, payload: Any) -> dict[str, Any]:
        if self.model is None:
            raise RuntimeError("Model failed to load at startup")
        prediction, payload_version_id = run_inference(self.model, payload)
        model_version_id = (
            payload_version_id
            if payload_version_id != "unknown"
            else os.environ.get("MODEL_VERSION_ID", "unknown")
        )
        return {
            "success": True,
            "prediction": prediction,
            "confidence": None,
            "project_id": os.environ.get("PROJECT_ID", "unknown"),
            "model_version_id": str(model_version_id),
            "engine": "deep-learning-serving",
        }

    @bentoml.api(route="/health", batchable=False)
    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "model_loaded": self.model is not None,
            "runtime": "deep-learning-serving-bentoml",
            "project_id": os.environ.get("PROJECT_ID", "unknown"),
            "model_version_id": os.environ.get("MODEL_VERSION_ID", "unknown"),
            "engine": "deep-learning-serving",
        }


DeepLearningModelService.add_asgi_middleware(
    RequestLoggingMiddleware,
    service="deep-learning-serving",
)
