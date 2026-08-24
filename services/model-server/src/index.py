import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
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
from src.database import get_model_version_record, model_registry_engine, verify_project_api_key

JWKS_URL = os.environ.get("JWKS_URL", "http://control-plane:8000/api/auth/.well-known/jwks.json")
REDPANDA_BROKERS = os.environ.get("REDPANDA_BROKERS", "redpanda:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "mlops_paas_production_data")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/1")
DEEP_LEARNING_FLAVORS = frozenset({"pytorch", "tensorflow"})


def create_redis_client():
    try:
        client = redis.from_url(REDIS_URL)
        client.ping()
        print(f"Redis Connected: {REDIS_URL}")
        return client
    except Exception as exc:
        print(f"Failed to connect to Redis: {exc}")
        return None


def create_kafka_producer():
    try:
        producer = Producer({
            "bootstrap.servers": REDPANDA_BROKERS,
            "client.id": "central-model-server",
            "linger.ms": 5,
        })
        print(f"Redpanda Connected: {REDPANDA_BROKERS} - Topic: {KAFKA_TOPIC}")
        return producer
    except Exception as exc:
        print(f"Failed to setup Redpanda producer: {exc}")
        return None


redis_client = None
kafka_producer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, kafka_producer
    redis_client = create_redis_client()
    kafka_producer = create_kafka_producer()
    yield
    if kafka_producer:
        kafka_producer.flush(timeout=5.0)

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

class InferenceRequest(BaseModel):
    features: Dict[str, Any]

async def get_public_key(kid: str):
    if kid not in JWKS_CACHE:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(JWKS_URL, timeout=5.0)
                response.raise_for_status()
                jwks = response.json()
                for key_data in jwks.get("keys", []):
                    if key_data.get("kid") == kid:
                        public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
                        JWKS_CACHE[kid] = public_key
                        return public_key
        except Exception as exc:
            print(f"Failed to fetch or parse JWKS: {exc}")
            return None
    return JWKS_CACHE.get(kid)

async def verify_model_access(
    version_id: str,
    api_key: str = Security(api_key_header),
    authorization: str = Header(None),
):
    try:
        uuid.UUID(version_id)
        model_record = get_model_version_record(version_id, redis_client=redis_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    if not model_record:
        raise HTTPException(status_code=404, detail="Model version not found.")
        
    model_tenant_id = model_record["tenant_id"]

    if model_record["access_mode"] == "public":
        return {"tenant_id": model_tenant_id, "auth_type": "public", "model_record": model_record}

    if api_key:
        key_record = verify_project_api_key(api_key, model_record["project_pk"])
        if not key_record:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid or revoked API Key")
        cached_tenant_id = key_record["tenant_id"]
        if cached_tenant_id != model_tenant_id:
            raise HTTPException(status_code=403, detail="Forbidden: You do not have permission to access this model.")
            
        return {"tenant_id": cached_tenant_id, "auth_type": "api_key", "model_record": model_record}

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Missing API Key or Bearer Token")

    token = authorization.split(" ")[1]

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Unauthorized: JWT missing 'kid' header")

        public_key = await get_public_key(kid)
        if not public_key:
            raise HTTPException(status_code=401, detail="Unauthorized: Unable to verify token signature")

        payload = jwt.decode(token, public_key, algorithms=["RS256"], audience="mlops-paas")
        token_tenant_id = payload.get("tenant_id")
        if token_tenant_id != model_tenant_id:
            raise HTTPException(status_code=403, detail="Forbidden: You do not have permission to access this model.")

        payload["auth_type"] = "jwt"
        payload["model_record"] = model_record
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Unauthorized: Token has expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Unauthorized: Invalid token ({exc})")

def send_to_redpanda(
    tenant_id: str,
    project_id: str,
    model_version_id: str,
    features_dict: dict,
    prediction_result: Any,
):
    if kafka_producer is None:
        return

    try:
        payload = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "project_id": project_id,
            "model_version_id": model_version_id,
            "timestamp": datetime.utcnow().isoformat(),
            "features": features_dict,
            "prediction": prediction_result,
        }

        kafka_producer.produce(
            topic=KAFKA_TOPIC,
            key=payload["id"].encode("utf-8"),
            value=json.dumps(payload).encode("utf-8"),
        )
        kafka_producer.poll(0)
    except Exception as exc:
        print(f"Error sending log to Redpanda: {exc}")

def serving_engine_for_flavor(flavor: Any) -> str:
    normalized_flavor = str(flavor or "").strip().lower()
    return "dl" if normalized_flavor in DEEP_LEARNING_FLAVORS else "ml"


def resolve_worker_url(model_record: Dict[str, Any], endpoint_path: str) -> str:
    serving_engine = serving_engine_for_flavor(model_record.get("flavor"))
    target_port = 5001 if serving_engine == "ml" else 5002
    container_name = model_record.get("endpoint_container_name")

    if not container_name:
        if os.environ.get("KUBERNETES_SERVICE_HOST"):
            # On K8s there is no shared fallback pod — fail clearly.
            raise HTTPException(
                status_code=503,
                detail=(
                    "Model endpoint is not deployed yet. "
                    "Please trigger a deployment from the Control Plane first."
                ),
            )
        # Docker Compose local-dev: fall back to named service so images can be tested individually without a full deploy cycle.
        fallback_host = "machine-learning-serving" if serving_engine == "ml" else "deep-learning-serving"
        return f"http://{fallback_host}:{target_port}{endpoint_path}"

    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        service_name = f"{container_name}-svc" if not container_name.endswith("-svc") else container_name
        runtime_namespace = os.environ.get("MODEL_RUNTIME_NAMESPACE", "mlops-model-runtimes").strip()
        host = f"{service_name}.{runtime_namespace}.svc.cluster.local"
    else:
        host = container_name
    return f"http://{host}:{target_port}{endpoint_path}"

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
    worker_url = resolve_worker_url(model_record, "/predict")
    features_dict = payload.features
    tenant_id = model_record["tenant_id"]
    project_id = str(model_record["project_id"])
    resolved_model_version_id = str(model_record["id"])
    start_time = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            worker_payload = {
                "features": features_dict,
                "model_version_id": resolved_model_version_id,
            }
            response = await client.post(worker_url, json=worker_payload)
            
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
                
            data = response.json()
            if isinstance(data, dict):
                prediction_result = data.get("prediction")
                confidence = data.get("confidence")
                engine = data.get("engine", serving_engine_for_flavor(model_record.get("flavor")))
            elif isinstance(data, list):
                prediction_result = data
                confidence = None
                engine = "deep-learning-serving"
            else:
                prediction_result = data
                confidence = None
                engine = serving_engine_for_flavor(model_record.get("flavor"))

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
            )

            return JSONResponse(
                content={
                    "success": True,
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
        raise HTTPException(status_code=503, detail=f"Service Unavailable: Cannot reach model serving pod ({exc})")
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
