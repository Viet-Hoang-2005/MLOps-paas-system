"""FastAPI adapter for the machine-learning serving worker."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.inference import run_inference
from src.loading import MODEL_CACHE, load_model_from_uri, load_summary
from src.logging_utils import RequestLoggingMiddleware, configure
from src.schemas import InferenceRequest


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure("machine-learning-serving")
    try:
        yield
    finally:
        load_summary.close()


app = FastAPI(
    title="AI PaaS Machine Learning Serving Engine",
    description="Dedicated stateless worker engine for Sklearn/XGBoost models.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware, routes=app.router.routes)


@app.get("/")
async def health_check():
    return {
        "status": "healthy",
        "engine": "machine-learning-serving",
        "cached_models": list(MODEL_CACHE.keys()),
    }


@app.get("/health")
async def model_health():
    model_version_id = os.environ.get("MODEL_VERSION_ID")
    if not model_version_id or model_version_id == "unknown":
        return {
            "status": "healthy",
            "model_loaded": False,
            "engine": "machine-learning-serving",
            "message": "Waiting for MODEL_VERSION_ID specification.",
        }
    try:
        model_uri = os.environ.get("MODEL_URI", "")
        if not model_uri:
            return {
                "status": "unhealthy",
                "model_loaded": False,
                "engine": "machine-learning-serving",
                "message": "MODEL_URI env var is missing.",
            }
        loaded = load_model_from_uri(
            model_version_id,
            model_uri,
            os.environ.get("MODEL_VERSION", "latest"),
        )
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
    model_version_id = str(payload.model_version_id) if payload.model_version_id else os.environ.get("MODEL_VERSION_ID")
    if not model_version_id or model_version_id == "unknown":
        raise HTTPException(status_code=400, detail="Missing model_version_id in request or environment.")
    model_uri = os.environ.get("MODEL_URI", "")
    if not model_uri:
        raise HTTPException(status_code=503, detail="MODEL_URI environment variable is empty.")

    loaded_model = load_model_from_uri(
        model_version_id,
        model_uri,
        os.environ.get("MODEL_VERSION", "latest"),
    )
    try:
        prediction, confidence = run_inference(loaded_model, payload.features)
        return JSONResponse(
            content={
                "success": True,
                "prediction": prediction,
                "confidence": confidence,
                "tenant_id": os.environ.get("TENANT_ID", "unknown"),
                "project_id": os.environ.get("PROJECT_ID", "unknown"),
                "model_version_id": str(model_version_id),
                "engine": "machine-learning-serving",
            },
            status_code=200,
        )
    except KeyError as exc:
        missing = exc.args[0]
        raise HTTPException(
            status_code=400,
            detail=f"Bad Request: Missing {len(missing)} required features (e.g., {list(missing)[:3]})",
        )
    except HTTPException:
        raise
    except ValueError as exc:
        message = str(exc)
        if "feature names" in message.lower() or "feature_names" in message.lower():
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Invalid feature columns",
                    "message": message,
                    "received_features": list(payload.features),
                    "hint": "The input columns do not match the model's training features.",
                },
            )
        raise HTTPException(status_code=400, detail=message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
