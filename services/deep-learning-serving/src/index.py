import logging
import os
import bentoml
import mlflow.pyfunc
import pandas as pd
from typing import Any, Dict
from src.loading import download_model_artifact, resolve_mlflow_model_dir

logger = logging.getLogger("bentoml.paas_service")


def load_runtime_model(model_version_id: str, model_uri: str | None):
    model_dir = "/app/model_artifact"
    if model_uri:
        source_dir = download_model_artifact(model_version_id, model_uri)
        model_dir = str(resolve_mlflow_model_dir(source_dir))
    elif not os.path.exists(model_dir):
        model_dir = "."
    logger.info("Loading Deep Learning model from %s...", model_dir)
    return mlflow.pyfunc.load_model(model_dir)

@bentoml.service(
    resources={"cpu": "2"},
    traffic={"timeout": 60},
)
class DeepLearningModelService:
    def __init__(self):
        model_version_id_str = os.environ.get("MODEL_VERSION_ID")
        model_uri = os.environ.get("MODEL_URI")
        model_version_id = (
            model_version_id_str if model_version_id_str and model_version_id_str != "unknown" else "unknown"
        )
        try:
            self.model = load_runtime_model(model_version_id, model_uri)
            logger.info("Model loaded successfully via mlflow.pyfunc!")
        except Exception as exc:
            logger.error("Error loading DL model version %s: %s", model_version_id, exc)
            self.model = None

    @bentoml.api(route="/predict", batchable=False)
    def predict(self, payload: Any) -> Dict[str, Any]:
        if self.model is None:
            raise RuntimeError("Model failed to load at startup")

        features = payload.get("features", payload) if isinstance(payload, dict) else payload
        model_version_id = (
            payload.get("model_version_id")
            if isinstance(payload, dict)
            else os.environ.get("MODEL_VERSION_ID", "unknown")
        )

        if isinstance(features, dict):
            if all(isinstance(v, (list, tuple, pd.Series)) for v in features.values()):
                df = pd.DataFrame(features)
            else:
                df = pd.DataFrame([features])
        elif isinstance(features, list):
            df = pd.DataFrame(features)
        elif isinstance(features, pd.DataFrame):
            df = features
        else:
            df = pd.DataFrame(features)

        preds = self.model.predict(df)
        if hasattr(preds, "tolist"):
            result = preds.tolist()
        else:
            result = list(preds)
        prediction = result[0] if isinstance(result, list) and len(result) == 1 else result
        return {
            "success": True,
            "prediction": prediction,
            "confidence": None,
            "project_id": os.environ.get("PROJECT_ID", "unknown"),
            "model_version_id": str(model_version_id),
            "engine": "deep-learning-serving",
        }

    @bentoml.api(route="/health", batchable=False)
    def health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "model_loaded": self.model is not None,
            "runtime": "deep-learning-serving-bentoml",
            "project_id": os.environ.get("PROJECT_ID", "unknown"),
            "model_version_id": os.environ.get("MODEL_VERSION_ID", "unknown"),
            "engine": "deep-learning-serving",
        }
