import os
import numpy as np
import pandas as pd
from typing import Any, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from src.loading import load_model_from_uri, MODEL_CACHE

app = FastAPI(
    title="AI PaaS Machine Learning Serving Engine",
    description="Dedicated stateless worker engine for Sklearn/XGBoost models.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class InferenceRequest(BaseModel):
    features: Dict[str, Any]
    model_version_id: str | None = None

@app.get("/")
async def health_check():
    return {
        "status": "healthy",
        "engine": "machine-learning-serving",
        "cached_models": list(MODEL_CACHE.keys()),
    }

@app.get("/health")
async def model_health():
    resolved_id_str = os.environ.get("MODEL_VERSION_ID")
    if not resolved_id_str or resolved_id_str == "unknown":
        return {
            "status": "healthy",
            "model_loaded": False,
            "engine": "machine-learning-serving",
            "message": "Waiting for MODEL_VERSION_ID specification."
        }
        
    try:
        model_version_id = resolved_id_str
        model_uri = os.environ.get("MODEL_URI", "")
        version_marker = os.environ.get("MODEL_VERSION", "latest")
        if not model_uri:
            return {
                "status": "unhealthy",
                "model_loaded": False,
                "engine": "machine-learning-serving",
                "message": "MODEL_URI env var is missing."
            }
        loaded = load_model_from_uri(model_version_id, model_uri, version_marker)
        return {
            "status": "healthy",
            "tenant_id": os.environ.get("TENANT_ID", "unknown"),
            "project_id": os.environ.get("PROJECT_ID", "unknown"),
            "model_version_id": str(model_version_id),
            "model_loaded": loaded.get("model") is not None,
            "engine": "machine-learning-serving",
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "model_loaded": False,
            "error": str(exc),
            "engine": "machine-learning-serving",
        }

@app.post("/predict")
async def predict(payload: InferenceRequest):
    model_version_id_env = os.environ.get("MODEL_VERSION_ID")
    resolved_id_str = str(payload.model_version_id) if payload.model_version_id else model_version_id_env
    
    if not resolved_id_str or resolved_id_str == "unknown":
        raise HTTPException(status_code=400, detail="Missing model_version_id in request or environment.")
        
    model_version_id = resolved_id_str

    model_uri = os.environ.get("MODEL_URI", "")
    version_marker = os.environ.get("MODEL_VERSION", "latest")
    if not model_uri:
        raise HTTPException(status_code=503, detail="MODEL_URI environment variable is empty.")

    loaded_model = load_model_from_uri(model_version_id, model_uri, version_marker)
    model = loaded_model["model"]
    expected_features = loaded_model.get("expected_features")

    try:
        features_dict = payload.features

        if expected_features:
            missing_cols = set(expected_features) - set(features_dict.keys())
            if missing_cols:
                raise HTTPException(
                    status_code=400,
                    detail=f"Bad Request: Missing {len(missing_cols)} required features (e.g., {list(missing_cols)[:3]})",
                )

        df_input = pd.DataFrame([features_dict])
        if expected_features:
            df_input = df_input[expected_features]

        prediction = model.predict(df_input)

        if isinstance(prediction, (np.ndarray, pd.Series)):
            result = prediction.tolist()
        else:
            result = prediction if isinstance(prediction, list) else [prediction]

        single_result = result[0] if len(result) > 0 else result
        while isinstance(single_result, list) and len(single_result) > 0:
            single_result = single_result[0]

        label_mapping = loaded_model.get("label_mapping")
        if label_mapping is not None:
            str_result = str(single_result)
            if single_result in label_mapping:
                single_result = label_mapping[single_result]
            elif str_result in label_mapping:
                single_result = label_mapping[str_result]
            elif type(single_result) in (int, float):
                if int(single_result) in label_mapping:
                    single_result = label_mapping[int(single_result)]

        confidence = None
        try:
            raw_model = getattr(model, "_model_impl", None)
            if not raw_model and hasattr(model, "unwrap_python_model"):
                raw_model = model.unwrap_python_model()
            if hasattr(raw_model, "predict_proba"):
                proba = raw_model.predict_proba(df_input)
                if hasattr(proba, "tolist"):
                    proba = proba.tolist()
                if isinstance(proba, list) and len(proba) > 0:
                    confidence = round(max(proba[0]) * 100, 2)
        except Exception:
            pass

        return JSONResponse(
            content={
                "success": True,
                "prediction": single_result,
                "confidence": confidence,
                "tenant_id": os.environ.get("TENANT_ID", "unknown"),
                "project_id": os.environ.get("PROJECT_ID", "unknown"),
                "model_version_id": str(model_version_id),
                "engine": "machine-learning-serving",
            },
            status_code=200,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        exc_str = str(exc)
        if "feature names" in exc_str.lower() or "feature_names" in exc_str.lower():
            received = list(payload.features.keys())
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Invalid feature columns",
                    "message": exc_str,
                    "received_features": received,
                    "hint": "The input columns do not match the model's training features.",
                },
            )
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
