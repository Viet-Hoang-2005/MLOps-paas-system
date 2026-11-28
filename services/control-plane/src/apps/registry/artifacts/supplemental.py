import uuid
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.observability.lifecycle import record_registry_event
from apps.registry.models import ModelArtifact, ModelVersion
from apps.registry.versions.registration import (
    _ARTIFACT_LABELS,
    _JSON_SUPPLEMENTAL_KINDS,
    _MAX_SUPPLEMENTAL_JSON_BYTES,
    _SNAPSHOT_SUMMARY_KINDS,
    _SUMMARY_OBJECT_KINDS,
)
from common.validation.artifacts import MAX_REFERENCE_DATA_BYTES
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import version_prefix
from infrastructure.storage.staged_csv import resolve_csv_upload


@dataclass
class _SupplementalUpload:
    kind: str
    name: str
    content_type: str
    body: bytes | None
    directory: str
    extra_metadata: dict = field(default_factory=dict)
    event_label: str = ""
    event_metadata: dict = field(default_factory=dict)
    summary: object = None


def _reference_upload(filename, body):
    return _SupplementalUpload(
        kind="reference_data",
        name=filename,
        content_type="text/csv",
        body=body,
        directory="reference",
        extra_metadata={"format": "csv"},
        event_label=f"reference data {filename}",
        event_metadata={"kind": "reference_data", "name": filename, "format": "csv"},
    )


def _prepare_supplemental_uploads(*, source_code_file, reference_data_file, json_files) -> list[_SupplementalUpload]:
    """Validate every upload and keep its bytes. Touches neither the database nor S3."""
    import json
    from pathlib import Path

    from apps.catalog.running.snapshots import parse_label_mapping_payload
    from common.validation.artifacts import (
        MAX_SOURCE_CODE_BYTES,
        validate_reference_data_content,
        validate_source_code_content,
    )

    prepared = []
    if source_code_file:
        name = Path(getattr(source_code_file, "name", "source_code.py").replace("\\", "/")).name
        body = source_code_file.read(MAX_SOURCE_CODE_BYTES + 1)
        filename = validate_source_code_content(name, body, error_key="source_code_file")
        prepared.append(
            _SupplementalUpload(
                kind="source_code",
                name=filename,
                content_type="text/x-python",
                body=body,
                directory="source",
                event_label=f"source code {filename}",
                event_metadata={"kind": "source_code", "name": filename},
            )
        )
    if reference_data_file:
        name = Path(getattr(reference_data_file, "name", "reference_data.csv").replace("\\", "/")).name
        body = reference_data_file.read(MAX_REFERENCE_DATA_BYTES + 1)
        filename, _ = validate_reference_data_content(name, body, error_key="reference_data_file")
        prepared.append(_reference_upload(filename, body))
    for kind in _JSON_SUPPLEMENTAL_KINDS:
        f_obj = json_files.get(kind)
        if not f_obj:
            continue
        filename = getattr(f_obj, "name", f"{kind}.json")
        if not filename.lower().endswith(".json"):
            raise ValidationError({kind: f"{kind} must be a .json file."})
        try:
            raw_bytes = f_obj.read(_MAX_SUPPLEMENTAL_JSON_BYTES + 1)
            if len(raw_bytes) > _MAX_SUPPLEMENTAL_JSON_BYTES:
                raise ValueError("JSON file exceeds 4 MiB.")
            if kind == "label_mapping":
                raw_content = parse_label_mapping_payload(filename, raw_bytes)
            else:
                raw_content = json.loads(raw_bytes.decode("utf-8"))
            if kind in _SUMMARY_OBJECT_KINDS and not isinstance(raw_content, dict):
                raise ValueError("Expected a JSON object.")
            if kind == "feature_importance" and not isinstance(raw_content, (dict, list)):
                raise ValueError("Expected a JSON object or array.")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValidationError({kind: "Upload a valid JSON file under 4 MiB."}) from exc
        prepared.append(
            _SupplementalUpload(
                kind=kind,
                name=filename,
                content_type="application/json",
                body=raw_bytes,
                directory=kind,
                extra_metadata={"summary": raw_content},
                summary=raw_content,
                event_label=f"{kind} {filename}",
                event_metadata={"kind": kind, "name": filename},
            )
        )
    return prepared


def _check_supplemental_allowed(version, project, uploads) -> None:
    """Reject uploads the version cannot accept. Runs before S3 and again under the lock."""
    from common.api.exceptions import Conflict

    if getattr(project, "deletion_state", "active") != "active" or version.deletion_requested:
        raise Conflict("This project or model version is being deleted.")
    existing = set(version.artifacts.filter(kind__in=[u.kind for u in uploads]).values_list("kind", flat=True))
    snapshot = {
        "metrics": version.metrics_summary,
        "params": version.params_summary,
        "model_insights": version.insights_summary,
        "feature_importance": version.insights_summary,
    }
    for upload in uploads:
        if upload.kind in existing:
            label = _ARTIFACT_LABELS.get(upload.kind, upload.kind)
            raise Conflict(f"This version already has a {label} artifact and cannot be replaced.")
        if upload.kind in _SNAPSHOT_SUMMARY_KINDS and isinstance(upload.summary, dict):
            overlap = set(upload.summary) & set(snapshot.get(upload.kind) or {})
            if overlap:
                raise ValidationError(
                    {upload.kind: f"Keys already exist in the registered snapshot: {', '.join(sorted(overlap))}."}
                )


def add_supplemental_artifacts(
    *,
    version,
    actor,
    source_code_file=None,
    reference_data_file=None,
    csv_upload_token=None,
    label_mapping_file=None,
    input_schema_file=None,
    metrics_file=None,
    params_file=None,
    model_insights_file=None,
    feature_importance_file=None,
    storage=None,
):
    """Attach supplemental artifacts to a version.

    No row lock is held across network I/O:
    1. validate the files and pre-check the version (no lock, no S3),
    2. upload to S3 under unique keys (no lock),
    3. re-check and write the rows in a short transaction under the project lock.
    Uploaded objects are removed if any later step fails.
    """


    json_files = {
        "label_mapping": label_mapping_file,
        "input_schema": input_schema_file,
        "metrics": metrics_file,
        "params": params_file,
        "model_insights": model_insights_file,
        "feature_importance": feature_importance_file,
    }
    if not source_code_file and not reference_data_file and csv_upload_token is None and not any(json_files.values()):
        raise ValidationError({"artifacts": "No supplemental artifact provided."})

    storage = storage or S3Storage()
    uploads = _prepare_supplemental_uploads(
        source_code_file=source_code_file, reference_data_file=reference_data_file, json_files=json_files
    )
    staged_csv = None
    if csv_upload_token is not None:
        if reference_data_file is not None:
            raise ValidationError({"reference_data_file": "Send either a CSV file or an upload token."})
        staged_csv = resolve_csv_upload(csv_upload_token, version, "version", error_field="reference_data_file")
        uploads.append(_reference_upload(staged_csv.filename, None))

    current = ModelVersion.objects.select_related("project__owner").get(pk=version.pk)
    _check_supplemental_allowed(current, current.project, uploads)
    prefix = version_prefix(current.project.owner.tenant_id, current.project.public_id, current.public_id)

    uploaded_uris = []
    try:
        stored_objects = []
        for upload in uploads:
            # A unique key keeps a request that loses the race from deleting the object
            # the winner just stored.
            key = f"{prefix}/artifacts/supplemental/{upload.directory}/{uuid.uuid4().hex}/{upload.name}"
            if staged_csv and upload.kind == "reference_data":
                stored = staged_csv.promote(storage, key)
            else:
                stored = storage.put(key, upload.body, upload.content_type)
            uploaded_uris.append(stored.uri)
            stored_objects.append(stored)

        with transaction.atomic():
            project = type(version.project).objects.select_for_update().get(pk=version.project_id)
            locked = ModelVersion.objects.select_for_update().filter(pk=version.pk).first()
            if locked is None:
                from common.api.exceptions import Conflict

                raise Conflict("This model version was deleted during upload.")
            _check_supplemental_allowed(locked, project, uploads)
            uploaded_at = timezone.now().isoformat()
            for upload, stored in zip(uploads, stored_objects, strict=True):
                ModelArtifact.objects.create(
                    version=locked,
                    kind=upload.kind,
                    name=upload.name,
                    uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type=upload.content_type,
                    metadata={
                        "provenance": "supplemental_upload",
                        "uploaded_by": getattr(actor, "email", "system"),
                        "uploaded_at": uploaded_at,
                        **upload.extra_metadata,
                    },
                )
                record_registry_event(
                    version=locked,
                    actor=actor,
                    event_type="artifact_added",
                    message=f"Added supplemental {upload.event_label}",
                    metadata=upload.event_metadata,
                )
    except Exception:
        for uri in uploaded_uris:
            try:
                storage.delete(uri)
            except Exception:
                pass
        raise

    return locked


def get_version_reference_preview(version, storage=None) -> dict:
    from io import BytesIO

    from common.validation.artifacts import parse_reference_preview_stream

    storage = storage or S3Storage()
    artifact = version.artifacts.filter(kind="reference_data").first()
    if not artifact or not artifact.uri:
        raise ValidationError({"reference_data": "This version does not have a reference dataset."})
    try:
        if hasattr(storage, "open_stream"):
            body, _, _ = storage.open_stream(artifact.uri)
            try:
                return parse_reference_preview_stream(body, artifact.name, max_rows=100)
            finally:
                body.close()
        raw = storage.read(artifact.uri, max_bytes=MAX_REFERENCE_DATA_BYTES)
        return parse_reference_preview_stream(BytesIO(raw), artifact.name, max_rows=100)
    except Exception as exc:
        raise ValidationError({"reference_data": "Could not read reference data from storage."}) from exc
