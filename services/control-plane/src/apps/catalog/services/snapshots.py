import json
import logging
import uuid
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from rest_framework.exceptions import NotFound, ValidationError

from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage

logger = logging.getLogger(__name__)


def _effective_version(project, version_id=None):
    if not project.active_deployment_id or project.active_deployment.status != "succeeded":
        raise Conflict("This project has no Running deployment.")
    version = project.active_deployment.version
    if version_id:
        try:
            requested_id = uuid.UUID(str(version_id))
        except ValueError as exc:
            raise NotFound("Version not found in this project.") from exc
        if requested_id == version.public_id:
            return version
        if project.versions.filter(public_id=requested_id).exists():
            raise Conflict("The requested version is not Running.")
        raise NotFound("Version not found in this project.")
    return version


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
    """Parse untrusted JSON label mappings without executing uploaded content."""
    if not filename.lower().endswith(".json"):
        raise ValidationError({"label_mapping": "Label mapping must be a JSON file."})
    try:
        raw = json.loads(payload_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValidationError({"label_mapping": "Upload a valid JSON label mapping."}) from exc
    if not isinstance(raw, (dict, list)):
        raise ValidationError({"label_mapping": "Label mapping must be a JSON object or array."})
    values = enumerate(raw) if isinstance(raw, list) else raw.items()
    return {str(key): str(value) for key, value in values}


def _parse_artifact_data(uri, storage):
    bucket, key = storage.parse_uri(uri)
    obj = storage.client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"]
    try:
        return body.read(16 * 1024 * 1024)
    finally:
        body.close()


def running_label_mapping(project, version_id=None, storage=None):
    """Retrieve the label mapping from the active Running version."""
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

    return None


def running_attributes(project, version_id=None, storage=None):
    """Return all resolved attributes, metrics, hyperparameters, schema, and label mapping."""
    version = _effective_version(project, version_id=version_id)
    storage = storage or S3Storage()

    metrics = {}
    params = {}
    label_mapping = None
    input_schema = None
    artifacts_list = []
    summary_sources = {"metrics": {}, "params": {}, "model_insights": None, "feature_importance": None}
    supplemental_summaries = {}

    feature_importance = None
    model_insights = None

    if version:
        metrics = dict(version.metrics_summary or {})
        params = dict(version.params_summary or {})
        summary_sources["metrics"] = {key: "registered" for key in metrics}
        summary_sources["params"] = {key: "registered" for key in params}
        raw_insights = dict(version.insights_summary or {})
        if raw_insights.get("kind") == "feature_importance":
            feature_importance = raw_insights
            summary_sources["feature_importance"] = "registered"
        elif raw_insights:
            model_insights = raw_insights
            summary_sources["model_insights"] = "registered"

        for art in version.artifacts.all():
            supplemental = art.metadata.get("summary") if art.metadata.get("provenance") == "supplemental_upload" else None
            if supplemental is not None:
                supplemental_summaries[art.kind] = supplemental
                if art.kind == "metrics" and isinstance(supplemental, dict):
                    metrics.update(supplemental)
                    summary_sources["metrics"].update({key: "supplemental" for key in supplemental})
                elif art.kind == "params" and isinstance(supplemental, dict):
                    params.update(supplemental)
                    summary_sources["params"].update({key: "supplemental" for key in supplemental})
                elif art.kind == "feature_importance":
                    if not feature_importance:
                        feature_importance = (
                            {"kind": "feature_importance", "items": supplemental}
                            if isinstance(supplemental, list) else supplemental
                        )
                        summary_sources["feature_importance"] = "supplemental"
                elif art.kind == "model_insights":
                    if not model_insights:
                        model_insights = supplemental
                        summary_sources["model_insights"] = "supplemental"
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
            "summary_sources": summary_sources,
            "supplemental_summaries": supplemental_summaries,
        }


def preview_attributes(project, storage=None):
    """Read draft attributes independently of the Running snapshot API."""
    storage = storage or S3Storage()
    metrics = {}
    params = {}
    label_mapping = None
    input_schema = None
    feature_importance = None
    model_insights = None
    artifacts_list = []
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

    return _preview_attributes_result(
        metrics, params, model_insights, feature_importance, label_mapping, input_schema, artifacts_list
    )


def _preview_attributes_result(metrics, params, model_insights, feature_importance, label_mapping, input_schema, artifacts_list):
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
