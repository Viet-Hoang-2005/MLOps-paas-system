"""Explicit, revisioned build inputs. No metadata inference by filename."""

import hashlib
import json
import math
import uuid

from rest_framework.exceptions import ValidationError

from apps.training.models import TrainingOutput
from infrastructure.storage import S3Storage
from .output_index import public_outputs
from .storage_scope import training_prefix_for

SLOTS = ("label_mapping", "input_schema", "metrics", "params", "model_insights", "feature_importance")


def validate_json(raw, slot):
    if len(raw) > 1024**2:
        raise ValidationError({slot: "Advanced artifacts must not exceed 1 MiB."})

    def reject(value):
        raise ValueError("Non-finite JSON number.")

    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=reject)

        def finite(item):
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("Non-finite number.")
            if isinstance(item, dict):
                for child in item.values():
                    finite(child)
            elif isinstance(item, list):
                for child in item:
                    finite(child)

        finite(value)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError({slot: "Upload finite UTF-8 JSON."}) from exc
    allowed = (dict, list) if slot in {"label_mapping", "feature_importance"} else (dict,)
    if not isinstance(value, allowed):
        raise ValidationError({slot: "Unsupported JSON structure."})
    if slot == "metrics" and any(type(v) not in (int, float) for v in value.values()):
        raise ValidationError({slot: "Metrics must map names to finite numeric values."})
    if slot == "label_mapping" and (
        not value
        or any(not isinstance(v, (str, int, float)) for v in (value.values() if isinstance(value, dict) else value))
    ):
        raise ValidationError({slot: "Label mapping requires non-empty scalar labels."})
    if slot == "input_schema":
        if value.get("type") == "object" and isinstance(value.get("properties"), dict) and value["properties"]:
            required = value.get("required", [])
            if not isinstance(required, list) or any(
                not isinstance(key, str) or key not in value["properties"] for key in required
            ):
                raise ValidationError({slot: "Invalid required input fields."})
        elif (
            isinstance(value.get("inputs"), list)
            and value["inputs"]
            and all(
                isinstance(v, dict) and isinstance(v.get("name"), str) and isinstance(v.get("type"), str)
                for v in value["inputs"]
            )
        ):
            pass
        else:
            raise ValidationError({slot: "Provide an object JSON Schema or named MLflow inputs."})
    if slot == "model_insights" and not value:
        raise ValidationError({slot: "Model insights must be a non-empty JSON object."})
    if slot == "feature_importance":
        items = value.get("items") if isinstance(value, dict) else value
        mapping = (
            next(
                (value[key] for key in ("feature_importance", "coefficients") if isinstance(value.get(key), dict)), None
            )
            if isinstance(value, dict)
            else None
        )
        if items is None and mapping is None and slot == "feature_importance" and isinstance(value, dict):
            mapping = value
        if mapping is not None:
            valid = bool(mapping) and all(type(number) in (int, float) for number in mapping.values())
        else:
            valid = (
                isinstance(items, list)
                and bool(items)
                and all(
                    isinstance(item, dict)
                    and isinstance(item.get("name"), str)
                    and bool(item["name"].strip())
                    and type(item.get("value")) in (int, float)
                    for item in items
                )
            )
        if not valid:
            raise ValidationError({slot: "Provide named numeric importance/insight items."})
    return value


def importance_summary(value):
    """Normalize only the explicitly selected role for the version display."""
    if isinstance(value, list):
        return {"kind": "feature_importance", "items": value}
    mapping = next((value[key] for key in ("feature_importance", "coefficients") if isinstance(value.get(key), dict)), None)
    if mapping is None and isinstance(value.get("items"), list):
        return {**value, "kind": "feature_importance"}
    if mapping is None:
        mapping = value
    return {
        "kind": "feature_importance",
        "items": [{"name": name, "value": number} for name, number in mapping.items()],
    }


def prepare_selection(job, data, files, storage=None):
    storage = storage or S3Storage()
    if set(files) - {slot + "_file" for slot in SLOTS}:
        raise ValidationError("Unsupported artifact upload.")
    assets = {str(v.public_id): v for v in public_outputs(job)}
    model_id = str(data.get("model_id", ""))
    model = assets.get(model_id)
    if model is None or model.metadata.get("group") != "model":
        raise ValidationError({"model_id": "Select a model belonging to this job."})
    bucket, key = storage.parse_uri(model.s3_uri)
    if bucket != storage.bucket or not key.startswith(training_prefix_for(job) + "/output/files/"):
        raise ValidationError({"model_id": "Invalid model storage scope."})
    stored_model = storage.head(model.s3_uri)
    if stored_model.size_bytes != model.size_bytes or stored_model.checksum != model.checksum:
        raise ValidationError({"model_id": "Model checksum or size mismatch."})
    requested = data.get("artifacts") or {}
    if not isinstance(requested, dict) or set(requested) - set(SLOTS):
        raise ValidationError({"artifacts": "Invalid artifact slots."})
    selections, staged = {}, []
    try:
        for slot in SLOTS:
            entry = requested.get(slot)
            upload = files.get(slot + "_file")
            if entry and upload:
                raise ValidationError({slot: "Choose a file or upload, not both."})
            if upload:
                if not upload.name.lower().endswith(".json"):
                    raise ValidationError({slot: "Upload a JSON file."})
                if any(c in upload.name for c in ("/", "\\", "\x00")):
                    raise ValidationError({slot: "Use a plain JSON filename."})
                raw = upload.read(1024**2 + 1)
                validate_json(raw, slot)
                identifier = uuid.uuid4()
                stored = storage.put(
                    f"{training_prefix_for(job)}/output/supplemental/{identifier}.json", raw, "application/json"
                )
                asset = TrainingOutput(
                    public_id=identifier,
                    job=job,
                    kind="file",
                    relative_path=f"Metadata/uploads/{identifier}/{upload.name.rsplit('/', 1)[-1]}",
                    s3_uri=stored.uri,
                    checksum=hashlib.sha256(raw).hexdigest(),
                    size_bytes=len(raw),
                    content_type="application/json",
                    metadata={"contract": 2, "group": "metadata", "uploaded": True},
                )
                staged.append(asset)
            elif entry:
                asset = assets.get(str(entry))
                if (
                    asset is None
                    or asset.metadata.get("group") != "metadata"
                    or not asset.relative_path.lower().endswith(".json")
                    or asset.size_bytes > 1024**2
                ):
                    raise ValidationError({slot: "Select a JSON metadata file from this job."})
                bucket, key = storage.parse_uri(asset.s3_uri)
                if bucket != storage.bucket or not key.startswith(training_prefix_for(job) + "/output/"):
                    raise ValidationError({slot: "Invalid metadata storage scope."})
                raw = storage.read(asset.s3_uri, max_bytes=1024**2 + 1)
                if hashlib.sha256(raw).hexdigest() != asset.checksum:
                    raise ValidationError({slot: "Metadata checksum mismatch."})
                validate_json(raw, slot)
            else:
                continue
            selections[slot] = str(asset.public_id)
        if (
            len(assets) + len(staged) > 20_000
            or sum(a.size_bytes for a in assets.values() if a.metadata.get("group") == "metadata")
            + sum(a.size_bytes for a in staged)
            > 512 * 1024**2
        ):
            raise ValidationError("Metadata exceeds the job file count or 512 MiB limit.")
        # Fingerprint file contents rather than staging UUIDs for HTTP replay.
        checksums = {
            slot: next((a.checksum for a in staged if str(a.public_id) == identifier), None)
            or assets[identifier].checksum
            for slot, identifier in selections.items()
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "model": model_id,
                    "artifacts": checksums,
                    "project": data.get("project_id") or data.get("new_project"),
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        return {"model_id": model_id, "artifacts": selections, "fingerprint": fingerprint}, staged
    except BaseException:
        for asset in staged:
            storage.delete(asset.s3_uri)
        raise
