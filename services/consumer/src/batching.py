"""Pure batch transformations for persisted inference events."""

import pandas as pd
from src.models import KafkaRecord


PREDICTION_RECORD_COLUMNS = (
    "public_id", "project_id", "model_version_id", "observed_at", "features",
    "prediction", "confidence", "latency_ms", "request_id",
)


def is_production_sample(payload: dict) -> bool:
    """Return whether an inference event can enter the CT candidate dataset."""
    event_id = payload.get("id") or payload.get("prediction_id")
    status_code = payload.get("status_code", 200)
    try:
        successful = 200 <= int(status_code) < 300
    except (TypeError, ValueError):
        successful = False
    return bool(event_id and isinstance(payload.get("features"), dict) and successful)


def build_prediction_records_dataframe(records: list[KafkaRecord]) -> pd.DataFrame:
    """Build replay-safe predictions from successful events without storing raw payloads."""
    rows = []
    for record in records:
        payload = record.payload
        if not is_production_sample(payload):
            continue
        event_id = str(payload.get("id") or payload["prediction_id"])
        rows.append(
            {
                "public_id": event_id,
                "project_id": payload.get("project_id"),
                "model_version_id": payload.get("model_version_id"),
                "observed_at": payload.get("timestamp"),
                "features": payload.get("features"),
                "prediction": payload.get("prediction"),
                "confidence": payload.get("confidence"),
                "latency_ms": payload.get("latency_ms"),
                "request_id": payload.get("request_id"),
            }
        )
    frame = pd.DataFrame(rows, columns=PREDICTION_RECORD_COLUMNS)
    for column in ("observed_at",):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    return frame


def build_automatic_drift_signals(
    records: list[KafkaRecord],
) -> list[dict[str, str]]:
    if not records:
        return []
    first, last = records[0], records[-1]
    model_version_ids = {
        str(record.payload["model_version_id"])
        for record in records
        if is_production_sample(record.payload) and record.payload.get("model_version_id")
    }
    batch_key = f"{first.topic}:{first.partition}:{first.offset}:{last.offset}"
    return [
        {
            "model_version_id": model_version_id,
            "idempotency_key": f"automatic-drift:{batch_key}:{model_version_id}",
        }
        for model_version_id in sorted(model_version_ids)
    ]
