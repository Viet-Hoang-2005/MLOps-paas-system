"""Inference event construction and Redpanda publication."""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any


def publish_inference_event(
    producer,
    summary,
    topic: str,
    tenant_id: str,
    project_id: str,
    model_version_id: str,
    features: dict,
    prediction: Any,
    *,
    prediction_id: str | None = None,
    confidence: float | None = None,
    latency_ms: float | None = None,
    status_code: int = 200,
    request_id: str | None = None,
) -> None:
    if producer is None:
        summary.record(success=False)
        summary.failure("publish", "Inference event producer unavailable")
        return
    started = time.perf_counter()
    try:
        record_id = prediction_id or str(uuid.uuid4())
        payload = {
            "id": record_id,
            "prediction_id": record_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "model_version_id": model_version_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "features": features,
            "prediction": prediction,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "status_code": status_code,
            "request_id": request_id,
        }
        producer.produce(
            topic=topic,
            key=record_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8"),
        )
        producer.poll(0)
        summary.record(
            duration_ms=(time.perf_counter() - started) * 1000,
            records=1,
        )
        summary.recovery("publish")
    except Exception as exc:
        summary.record(
            success=False,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        summary.failure(
            "publish",
            "Inference event enqueue failed",
            error_type=type(exc).__name__,
        )
