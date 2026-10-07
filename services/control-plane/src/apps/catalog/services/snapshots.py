import json
import logging
import pickle
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from rest_framework.exceptions import ValidationError

from infrastructure.storage import S3Storage

logger = logging.getLogger(__name__)


def _effective_version(project, version_id=None):
    if version_id and hasattr(project, "versions"):
        try:
            matched = project.versions.filter(public_id=version_id).first()
            if matched:
                return matched
        except Exception:
            pass
    if project.active_deployment_id:
        return project.active_deployment.version
    if hasattr(project, "versions") and project.versions.exists():
        return project.versions.order_by("-registered_at", "-id").first()
    return None


def running_source(project, version_id=None, storage=None):
    """Read only the immutable Running script; never execute or extract the archive."""
    version = _effective_version(project, version_id=version_id)
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
            raw = json.loads(payload_bytes.decode("utf-8-sig", errors="replace"))
            if isinstance(raw, list):
                return {str(idx): (str(val) if not isinstance(val, (str, int, float, bool)) else str(val)) for idx, val in enumerate(raw)}
            elif isinstance(raw, dict):
                return {str(k): (str(v) if not isinstance(v, (str, int, float, bool)) else str(v)) for k, v in raw.items()}
            return {"0": str(raw)}
        except Exception as exc:
            raise ValidationError(f"Could not parse JSON label mapping: {exc}")
    return {}


def _parse_artifact_data(uri, storage):
    bucket, key = storage.parse_uri(uri)
    obj = storage.client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"]
    try:
        return body.read(16 * 1024 * 1024)
    finally:
        body.close()


def running_label_mapping(project, version_id=None, storage=None):
    """Retrieve and deserialize the label mapping for the project's active deployment or latest version or preview."""
    version = _effective_version(project, version_id=version_id)
    storage = storage or S3Storage()
    if version:
        artifact = version.artifacts.filter(kind="label_mapping").first()
        if not artifact or not artifact.uri:
            return None
        try:
            payload = _parse_artifact_data(artifact.uri, storage)
            return {
                "filename": artifact.name,
                "mapping": parse_label_mapping_payload(artifact.name, payload),
            }
        except Exception as exc:
            logger.warning("Failed to parse label mapping %s for version %s: %s", artifact.name, getattr(version, "public_id", None), exc)
            return None

    preview = getattr(project, "preview", None)
    if preview:
        asset = preview.assets.filter(kind="label_mapping").first()
        if asset and asset.s3_uri:
            try:
                payload = _parse_artifact_data(asset.s3_uri, storage)
                return {
                    "filename": asset.name,
                    "mapping": parse_label_mapping_payload(asset.name, payload),
                }
            except Exception as exc:
                logger.warning("Failed to parse preview label mapping %s: %s", asset.name, exc)
                return None
    return None


def running_attributes(project, version_id=None, storage=None):
    """Return all resolved attributes, metrics, hyperparameters, schema, and label mapping."""
    version = _effective_version(project, version_id=version_id)
    storage = storage or S3Storage()

    metrics = {}
    params = {}
    insights = {}
    label_mapping = None
    input_schema = None
    artifacts_list = []

    feature_importance = None
    model_insights = None

    if version:
        metrics = dict(version.metrics_summary or {})
        params = dict(version.params_summary or {})
        raw_insights = dict(version.insights_summary or {})
        if raw_insights.get("kind") == "feature_importance":
            feature_importance = raw_insights
        elif raw_insights:
            model_insights = raw_insights

        for art in version.artifacts.all():
            artifacts_list.append({
                "kind": art.kind,
                "name": art.name,
                "size_bytes": art.size_bytes,
            })
            if art.kind == "label_mapping" and label_mapping is None and art.uri:
                try:
                    payload = _parse_artifact_data(art.uri, storage)
                    label_mapping = {
                        "filename": art.name,
                        "mapping": parse_label_mapping_payload(art.name, payload),
                    }
                except Exception as exc:
                    logger.warning("Failed to parse label mapping %s for version %s: %s", art.name, getattr(version, "public_id", None), exc)
            elif art.kind == "input_schema" and input_schema is None and art.uri:
                try:
                    payload = _parse_artifact_data(art.uri, storage)
                    input_schema = {
                        "filename": art.name,
                        "schema": json.loads(payload.decode("utf-8", errors="replace")),
                    }
                except Exception:
                    pass
            elif art.kind == "metrics" and not metrics and art.uri:
                try:
                    payload = _parse_artifact_data(art.uri, storage)
                    metrics = json.loads(payload.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            elif art.kind == "params" and not params and art.uri:
                try:
                    payload = _parse_artifact_data(art.uri, storage)
                    params = json.loads(payload.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            elif art.kind == "feature_importance" and not feature_importance and art.uri:
                try:
                    payload = _parse_artifact_data(art.uri, storage)
                    loaded_fi = json.loads(payload.decode("utf-8", errors="replace"))
                    if isinstance(loaded_fi, list):
                        feature_importance = {"kind": "feature_importance", "items": loaded_fi}
                    elif isinstance(loaded_fi, dict):
                        feature_importance = loaded_fi
                except Exception:
                    pass
            elif art.kind == "model_insights" and not model_insights and art.uri:
                try:
                    payload = _parse_artifact_data(art.uri, storage)
                    loaded_mi = json.loads(payload.decode("utf-8", errors="replace"))
                    if isinstance(loaded_mi, list):
                        model_insights = {"kind": "model_insights", "items": loaded_mi}
                    elif isinstance(loaded_mi, dict):
                        model_insights = loaded_mi
                except Exception:
                    pass

        return {
            "metrics": metrics,
            "params": params,
            "insights": model_insights or feature_importance or raw_insights or None,
            "model_insights": model_insights,
            "feature_importance": feature_importance,
            "label_mapping": label_mapping,
            "input_schema": input_schema,
            "artifacts": artifacts_list,
        }

    preview = getattr(project, "preview", None)
    if preview:
        for art in preview.assets.all():
            artifacts_list.append({
                "kind": art.kind,
                "name": art.name,
                "size_bytes": art.size_bytes,
            })
            uri = getattr(art, "s3_uri", None) or getattr(art, "uri", None)
            if not uri:
                continue
            if art.kind == "label_mapping" and label_mapping is None:
                try:
                    payload = _parse_artifact_data(uri, storage)
                    label_mapping = {
                        "filename": art.name,
                        "mapping": parse_label_mapping_payload(art.name, payload),
                    }
                except Exception as exc:
                    logger.warning("Failed to parse preview label mapping %s: %s", art.name, exc)
            elif art.kind == "input_schema" and input_schema is None:
                try:
                    payload = _parse_artifact_data(uri, storage)
                    input_schema = {
                        "filename": art.name,
                        "schema": json.loads(payload.decode("utf-8", errors="replace")),
                    }
                except Exception:
                    pass
            elif art.kind == "metrics" and not metrics:
                try:
                    payload = _parse_artifact_data(uri, storage)
                    metrics = json.loads(payload.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            elif art.kind == "params" and not params:
                try:
                    payload = _parse_artifact_data(uri, storage)
                    params = json.loads(payload.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            elif art.kind == "feature_importance" and not feature_importance:
                try:
                    payload = _parse_artifact_data(uri, storage)
                    loaded_fi = json.loads(payload.decode("utf-8", errors="replace"))
                    if isinstance(loaded_fi, list):
                        feature_importance = {"kind": "feature_importance", "items": loaded_fi}
                    elif isinstance(loaded_fi, dict):
                        feature_importance = loaded_fi
                except Exception:
                    pass
            elif art.kind == "model_insights" and not model_insights:
                try:
                    payload = _parse_artifact_data(uri, storage)
                    loaded_mi = json.loads(payload.decode("utf-8", errors="replace"))
                    if isinstance(loaded_mi, list):
                        model_insights = {"kind": "model_insights", "items": loaded_mi}
                    elif isinstance(loaded_mi, dict):
                        model_insights = loaded_mi
                except Exception:
                    pass

    return {
        "metrics": metrics,
        "params": params,
        "insights": model_insights or feature_importance or None,
        "model_insights": model_insights,
        "feature_importance": feature_importance,
        "label_mapping": label_mapping,
        "input_schema": input_schema,
        "artifacts": artifacts_list,
    }
