import json
import pickle
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from rest_framework.exceptions import ValidationError

from infrastructure.storage import S3Storage


def _effective_version(project):
    if project.active_deployment_id:
        return project.active_deployment.version
    if hasattr(project, "versions") and project.versions.exists():
        return project.versions.order_by("-registered_at", "-id").first()
    return None


def running_source(project, storage=None):
    """Read only the immutable Running script; never execute or extract the archive."""
    version = _effective_version(project)
    if not version:
        return ""
    asset = version.artifacts.filter(kind="source_code").first()
    if not asset:
        return ""
    storage = storage or S3Storage()
    bucket, key = storage.parse_uri(asset.uri)
    obj = storage.client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"]
    try:
        payload = body.read(32 * 1024 * 1024 + 1)
    finally:
        body.close()
    if len(payload) > 32 * 1024 * 1024:
        raise ValidationError("Source snapshot is too large to display.")
    if asset.name.lower().endswith(".zip"):
        entry = asset.metadata.get("entry_point", "")
        if not entry or not entry.lower().endswith(".py"):
            raise ValidationError("The training snapshot does not identify a Python entry point.")
        try:
            with ZipFile(BytesIO(payload)) as archive:
                info = archive.getinfo(entry)
                if info.file_size > 1024 * 1024:
                    raise ValidationError("The Python entry point is too large to display.")
                payload = archive.read(info)
        except (BadZipFile, KeyError) as exc:
            raise ValidationError("The source snapshot does not contain its entry point.") from exc
    return payload.decode("utf-8", errors="replace")


def parse_label_mapping_payload(filename: str, payload_bytes: bytes) -> dict:
    """Safely parse label mapping bytes (.json or .pkl) into a standard JSON-serializable dictionary."""
    if not payload_bytes:
        return {}
    lower = filename.lower()
    if lower.endswith(".pkl"):
        try:
            raw = pickle.loads(payload_bytes)
            if hasattr(raw, "tolist"):
                raw = raw.tolist()
            if isinstance(raw, (list, tuple)):
                return {str(idx): (str(val) if not isinstance(val, (str, int, float, bool)) else str(val)) for idx, val in enumerate(raw)}
            elif isinstance(raw, dict):
                return {str(k): (str(v) if not isinstance(v, (str, int, float, bool)) else str(v)) for k, v in raw.items()}
            return {"0": str(raw)}
        except Exception as exc:
            raise ValidationError(f"Could not parse pickle label mapping: {exc}")
    elif lower.endswith(".json"):
        try:
            raw = json.loads(payload_bytes.decode("utf-8", errors="replace"))
            if isinstance(raw, list):
                return {str(idx): (str(val) if not isinstance(val, (str, int, float, bool)) else str(val)) for idx, val in enumerate(raw)}
            elif isinstance(raw, dict):
                return {str(k): (str(v) if not isinstance(v, (str, int, float, bool)) else str(v)) for k, v in raw.items()}
            return {"0": str(raw)}
        except Exception as exc:
            raise ValidationError(f"Could not parse JSON label mapping: {exc}")
    return {}


def running_label_mapping(project, storage=None):
    """Retrieve and deserialize the label mapping for the project's active deployment or latest version."""
    version = _effective_version(project)
    if not version:
        return None
    artifact = version.artifacts.filter(kind="label_mapping").first()
    if not artifact or not artifact.uri:
        return None
    storage = storage or S3Storage()
    bucket, key = storage.parse_uri(artifact.uri)
    obj = storage.client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"]
    try:
        payload = body.read(16 * 1024 * 1024)
    finally:
        body.close()
    parsed = parse_label_mapping_payload(artifact.name, payload)
    return {
        "filename": artifact.name,
        "mapping": parsed,
    }


def running_attributes(project, storage=None):
    """Return all resolved attributes, metrics, hyperparameters, schema, and label mapping."""
    version = _effective_version(project)
    if not version:
        return {
            "metrics": {},
            "params": {},
            "insights": {},
            "label_mapping": None,
            "input_schema": None,
            "artifacts": [],
        }

    storage = storage or S3Storage()

    metrics = dict(version.metrics_summary or {})
    params = dict(version.params_summary or {})
    insights = dict(version.insights_summary or {})
    label_mapping = None
    input_schema = None

    artifacts_list = []
    for art in version.artifacts.all():
        artifacts_list.append({
            "kind": art.kind,
            "name": art.name,
            "size_bytes": art.size_bytes,
        })
        if art.kind == "label_mapping" and label_mapping is None and art.uri:
            try:
                bucket, key = storage.parse_uri(art.uri)
                obj = storage.client.get_object(Bucket=bucket, Key=key)
                body = obj["Body"]
                try:
                    payload = body.read(16 * 1024 * 1024)
                finally:
                    body.close()
                label_mapping = {
                    "filename": art.name,
                    "mapping": parse_label_mapping_payload(art.name, payload),
                }
            except Exception:
                pass
        elif art.kind == "input_schema" and input_schema is None and art.uri:
            try:
                bucket, key = storage.parse_uri(art.uri)
                obj = storage.client.get_object(Bucket=bucket, Key=key)
                body = obj["Body"]
                try:
                    payload = body.read(16 * 1024 * 1024)
                finally:
                    body.close()
                input_schema = {
                    "filename": art.name,
                    "schema": json.loads(payload.decode("utf-8", errors="replace")),
                }
            except Exception:
                pass
        elif art.kind == "metrics" and not metrics and art.uri:
            try:
                bucket, key = storage.parse_uri(art.uri)
                obj = storage.client.get_object(Bucket=bucket, Key=key)
                body = obj["Body"]
                try:
                    payload = body.read(16 * 1024 * 1024)
                finally:
                    body.close()
                metrics = json.loads(payload.decode("utf-8", errors="replace"))
            except Exception:
                pass
        elif art.kind == "params" and not params and art.uri:
            try:
                bucket, key = storage.parse_uri(art.uri)
                obj = storage.client.get_object(Bucket=bucket, Key=key)
                body = obj["Body"]
                try:
                    payload = body.read(16 * 1024 * 1024)
                finally:
                    body.close()
                params = json.loads(payload.decode("utf-8", errors="replace"))
            except Exception:
                pass
        elif art.kind in {"feature_importance", "model_insights"} and not insights and art.uri:
            try:
                bucket, key = storage.parse_uri(art.uri)
                obj = storage.client.get_object(Bucket=bucket, Key=key)
                body = obj["Body"]
                try:
                    payload = body.read(16 * 1024 * 1024)
                finally:
                    body.close()
                loaded_insights = json.loads(payload.decode("utf-8", errors="replace"))
                if isinstance(loaded_insights, list):
                    insights = {"kind": "feature_importance", "items": loaded_insights}
                elif isinstance(loaded_insights, dict):
                    insights = loaded_insights
            except Exception:
                pass

    return {
        "metrics": metrics,
        "params": params,
        "insights": insights,
        "label_mapping": label_mapping,
        "input_schema": input_schema,
        "artifacts": artifacts_list,
    }
