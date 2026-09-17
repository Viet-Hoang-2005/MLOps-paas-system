import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
import jwt
import redis
from confluent_kafka import Producer
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from jwt.algorithms import RSAAlgorithm
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from src.logging_utils import (
    Summary, bind_context, configure, current_context, get_logger, log_event,
    request_id as validated_request_id, reset_context,
)
from src.logging_utils import RequestLoggingMiddleware
from src import auth as auth_service
from src.events import publish_inference_event
from src.inference import parse_worker_prediction
from src.routing import resolve_worker_url, serving_engine_for_flavor
from src.schemas import InferenceRequest

logger = get_logger(__name__)
publication_summary = Summary(logger, "inference_enqueue_summary")
jwks_summary = Summary(logger, "jwks_fetch_summary")

from src.database import (
    _fetch_model_version_from_db,
    cache_summary,
    get_model_version_record,
    invalidate_model_version_cache,
    model_registry_engine,
    verify_project_api_key,
)

JWKS_URL = os.environ.get("JWKS_URL", "http://control-plane:8000/api/auth/.well-known/jwks.json")
REDPANDA_BROKERS = os.environ.get("REDPANDA_BROKERS", "redpanda:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "mlops_paas_production_data")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/1")


def create_redis_client():
    try:
        client = redis.from_url(REDIS_URL)
        client.ping()
        log_event(logger, "INFO", "redis_connected", "Redis connection established")
        return client
    except Exception as exc:
        log_event(logger, "ERROR", "redis_connection_failed", "Redis connection failed", error_type=type(exc).__name__)
        return None


def create_kafka_producer():
    try:
        producer = Producer({
            "bootstrap.servers": REDPANDA_BROKERS,
            "client.id": "central-model-server",
            "linger.ms": 5,
        })
        log_event(logger, "INFO", "producer_initialized", "Inference event producer initialized")
        return producer
    except Exception as exc:
        log_event(logger, "ERROR", "producer_initialization_failed", "Inference event producer initialization failed", error_type=type(exc).__name__)
        return None


redis_client = None
kafka_producer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, kafka_producer
    configure("model-server")
    redis_client = create_redis_client()
    kafka_producer = create_kafka_producer()
    try:
        yield
    finally:
        try:
            if kafka_producer:
                kafka_producer.flush(timeout=5.0)
        finally:
            publication_summary.close()
            jwks_summary.close()
            cache_summary.close()

app = FastAPI(
    title="AI PaaS Model Server Gateway",
    description="Model Server API Gateway handling Authentication, Routing to ML/DL Pods, and Kafka Redpanda Logging.",
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

paas_predictions_counter = Counter(
    "paas_predictions_total",
    "Total predictions processed",
    ["tenant_id", "project_id", "model_version_id", "status"],
)

paas_latency_histogram = Histogram(
    "paas_prediction_latency_seconds",
    "Latency of prediction requests",
    ["tenant_id", "project_id", "model_version_id"],
)

Instrumentator().instrument(app).expose(app)

JWKS_CACHE: Dict[str, Any] = {}
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_public_key(kid: str):
    return await auth_service.fetch_public_key(
        kid,
        cache=JWKS_CACHE,
        jwks_url=JWKS_URL,
        summary=jwks_summary,
        http_client_factory=httpx.AsyncClient,
        rsa_algorithm=RSAAlgorithm,
    )


async def verify_model_access(
    version_id: str,
    api_key: str = Security(api_key_header),
    authorization: str = Header(None),
):
    return await auth_service.authorize_model_access(
        version_id,
        api_key,
        authorization,
        redis_client=redis_client,
        get_model_version_record=get_model_version_record,
        verify_project_api_key=verify_project_api_key,
        get_public_key=get_public_key,
        jwt_module=jwt,
    )


def send_to_redpanda(
    tenant_id: str,
    project_id: str,
    model_version_id: str,
    features_dict: dict,
    prediction_result: Any,
    prediction_id: str | None = None,
    confidence: float | None = None,
    latency_ms: float | None = None,
    status_code: int = 200,
    request_id: str | None = None,
):
    return publish_inference_event(
        kafka_producer,
        publication_summary,
        KAFKA_TOPIC,
        tenant_id,
        project_id,
        model_version_id,
        features_dict,
        prediction_result,
        prediction_id=prediction_id,
        confidence=confidence,
        latency_ms=latency_ms,
        status_code=status_code,
        request_id=request_id,
    )


@app.get("/")
async def health_check():
    return {
        "status": "healthy",
        "mode": "central-model-server",
        "model_registry_connected": model_registry_engine is not None,
    }

@app.get("/models/{version_id}/health")
async def model_health(version_id: str, token_payload: dict = Depends(verify_model_access)):
    model_record = token_payload["model_record"]
    worker_url = resolve_worker_url(model_record, "/health")
    resolved_model_version_id = str(model_record.get("id", version_id))
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(worker_url)
            if response.status_code == 200:
                return response.json()
            return JSONResponse(
                status_code=response.status_code,
                content={"status": "unhealthy", "message": f"Worker health returned HTTP {response.status_code}", "detail": response.text}
            )
    except Exception as exc:
        invalidate_model_version_cache(resolved_model_version_id, redis_client=redis_client)
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "model_loaded": False, "error": f"Cannot reach worker pod: {exc}"}
        )

@app.post("/models/{version_id}/predict")
async def predict(
    version_id: str,
    request: Request,
    payload: InferenceRequest,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(verify_model_access),
):
    model_record = token_payload["model_record"]
    raw_request_id = request.headers.get("x-request-id") if hasattr(request, "headers") else None
    context = {
        "request_id": validated_request_id(current_context().get("request_id") or raw_request_id),
        "tenant_id": str(model_record["tenant_id"]),
        "project_id": str(model_record["project_id"]),
        "model_version_id": str(model_record["id"]),
    }
    # Only IDs from the authorized registry record enter resource log context.
    # State survives this handler's reset for the outer request middleware.
    if isinstance(getattr(request, "scope", None), dict):
        request.scope.setdefault("state", {})["mlops_log_context"] = context
    token = bind_context(**context)
    try:
        return await _predict(version_id, request, payload, background_tasks, token_payload)
    finally:
        reset_context(token)


async def _predict(
    version_id: str,
    request: Request,
    payload: InferenceRequest,
    background_tasks: BackgroundTasks,
    token_payload: dict,
):
    model_record = token_payload["model_record"]
    worker_url = resolve_worker_url(model_record, "/predict")
    features_dict = payload.features
    tenant_id = model_record["tenant_id"]
    project_id = str(model_record["project_id"])
    resolved_model_version_id = str(model_record["id"])
    prediction_id = str(uuid.uuid4())
    request_id = current_context()["request_id"]
    start_time = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            worker_payload = {
                "features": features_dict,
                "model_version_id": resolved_model_version_id,
            }
            response = await client.post(worker_url, json=worker_payload, headers={"X-Request-ID": request_id})
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            
            if response.status_code != 200:
                paas_predictions_counter.labels(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    model_version_id=resolved_model_version_id,
                    status=f"error_{response.status_code}",
                ).inc()
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                return JSONResponse(status_code=response.status_code, content=error_detail)
                
            prediction_result, confidence, engine = parse_worker_prediction(
                response.json(),
                model_record.get("flavor"),
            )

            paas_predictions_counter.labels(
                tenant_id=tenant_id,
                project_id=project_id,
                model_version_id=resolved_model_version_id,
                status="success",
            ).inc()
            background_tasks.add_task(
                send_to_redpanda,
                tenant_id,
                project_id,
                resolved_model_version_id,
                features_dict,
                prediction_result,
                prediction_id=prediction_id,
                confidence=confidence,
                latency_ms=latency_ms,
                status_code=200,
                request_id=request_id,
            )

            return JSONResponse(
                content={
                    "success": True,
                    "prediction_id": prediction_id,
                    "id": prediction_id,
                    "prediction": prediction_result,
                    "confidence": confidence,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "model_version_id": resolved_model_version_id,
                    "engine": engine,
                },
                status_code=200,
            )
    except httpx.RequestError as exc:
        paas_predictions_counter.labels(
            tenant_id=tenant_id,
            project_id=project_id,
            model_version_id=resolved_model_version_id,
            status="error_503",
        ).inc()
        # Reactive invalidation: evict stale routing cache immediately
        invalidate_model_version_cache(resolved_model_version_id, redis_client=redis_client)

        fresh_record = None
        try:
            fresh_record = _fetch_model_version_from_db(resolved_model_version_id)
        except Exception:
            fresh_record = None

        if fresh_record and (
            fresh_record.get("deployment_status") in {"stopped", "failed", "unhealthy"}
            or not fresh_record.get("endpoint_container_name")
        ):
            current_status = fresh_record.get("deployment_status") or "stopped"
            raise HTTPException(
                status_code=409,
                detail=f"Model deployment is not active (current status: '{current_status}'). Serving container is stopped or unavailable.",
            )

        raise HTTPException(
            status_code=503,
            detail=f"Service Unavailable: Cannot reach model serving pod ({exc}). Routing cache invalidated.",
        )
    except Exception as exc:
        paas_predictions_counter.labels(
            tenant_id=tenant_id,
            project_id=project_id,
            model_version_id=resolved_model_version_id,
            status="error_500",
        ).inc()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        paas_latency_histogram.labels(
            tenant_id=tenant_id,
            project_id=project_id,
            model_version_id=resolved_model_version_id,
        ).observe(time.perf_counter() - start_time)
