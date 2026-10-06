"""Revision-checked drafts and immutable build inputs."""

import json
import uuid
from pathlib import Path

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.artifact_types import validate_source_artifact
from apps.catalog.models import ModelPreview, PreviewAsset
from common.api.exceptions import Conflict
from common.validation.artifacts import (
    parse_reference_preview,
    validate_reference_data_file,
    validate_source_code_file,
)
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import project_prefix

FILE_FIELDS = {kind: f"{kind}_file" for kind, _ in PreviewAsset.KINDS}


def save_preview(*, project, data, storage=None, require_artifact=False):
    storage = storage or S3Storage()
    with transaction.atomic():
        project = type(project).objects.select_for_update().get(pk=project.pk)
        if not project.is_active or project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        preview = ModelPreview.objects.select_for_update().get(project=project)
        if data.get("revision") != preview.revision:
            raise Conflict("Preview changed in another session. Reload before saving.")
        flavor = data.get("flavor", preview.flavor)
        artifact_format = data.get("artifact_format", preview.artifact_format)
        uploaded = {kind: data[field] for kind, field in FILE_FIELDS.items() if data.get(field)}
        remove = set(data.get("remove_assets", []))
        artifact = uploaded.get("source_artifact")
        existing = preview.assets.filter(kind="source_artifact").first()
        if artifact or (existing and "source_artifact" not in remove):
            validate_source_artifact(
                filename=artifact.name if artifact else existing.name, flavor=flavor, artifact_format=artifact_format
            )
        elif require_artifact:
            raise ValidationError({"source_artifact_file": "A model artifact is required."})

        if "source_code" in uploaded:
            validate_source_code_file(uploaded["source_code"])

        if "reference_data" in uploaded:
            _, fmt = validate_reference_data_file(uploaded["reference_data"])
            uploaded["reference_data"].content_type = "text/csv" if fmt == "csv" else "application/vnd.apache.parquet"

        if "label_mapping" in uploaded and Path(uploaded["label_mapping"].name).suffix.lower() not in {".json", ".pkl"}:
            raise ValidationError({"label_mapping_file": "Unsupported file format."})

        for kind in ("metrics", "params", "model_insights", "feature_importance", "input_schema"):
            if kind in uploaded and Path(uploaded[kind].name).suffix.lower() != ".json":
                raise ValidationError({FILE_FIELDS[kind]: "Upload a JSON file."})
        for kind, file in uploaded.items():
            if Path(file.name).suffix.lower() != ".json":
                continue
            try:
                content = file.read(4 * 1024 * 1024 + 1)
                if len(content) > 4 * 1024 * 1024:
                    raise ValueError
                value = json.loads(content)
                if not isinstance(value, (dict, list)):
                    raise ValueError
                if kind in {"metrics", "params", "model_insights", "input_schema"} and not isinstance(value, dict):
                    raise ValueError
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValidationError({FILE_FIELDS[kind]: "Upload a valid JSON file under 4 MiB."}) from exc
            finally:
                file.seek(0)
        written = []
        try:
            for kind, file in uploaded.items():
                name = Path(file.name).name
                key = (
                    f"{project_prefix(project.owner.tenant_id, project.public_id)}/preview/{uuid.uuid4()}/{kind}/{name}"
                )
                stored = storage.put(key, file, file.content_type or "application/octet-stream")
                written.append(stored.uri)
                PreviewAsset.objects.update_or_create(
                    preview=preview,
                    kind=kind,
                    defaults={
                        "name": name,
                        "s3_uri": stored.uri,
                        "checksum": stored.checksum,
                        "size_bytes": stored.size_bytes,
                        "content_type": stored.content_type,
                    },
                )
            preview.assets.filter(kind__in=remove - set(uploaded)).delete()
            preview.flavor = flavor
            preview.artifact_format = artifact_format
            preview.requirements_text = data.get("requirements_text", preview.requirements_text)
            preview.revision += 1
            preview.save()
        except Exception:
            for uri in written:
                storage.delete(uri)
            raise
    return preview


def create_project_preview(*, actor, data):
    from apps.catalog.services.project_metadata import save_project_metadata

    with transaction.atomic():
        project = save_project_metadata(
            actor=actor,
            validated_data={key: data[key] for key in ("name", "description", "access_mode") if key in data},
        )
        save_preview(project=project, data={**data, "revision": project.preview.revision}, require_artifact=True)
        project.refresh_from_db()
    return project


def get_preview_reference_preview(project, storage=None) -> dict:
    storage = storage or S3Storage()
    preview = project.preview
    asset = preview.assets.filter(kind="reference_data").first()
    if not asset or not asset.s3_uri:
        raise ValidationError({"reference_data": "This project preview does not have a reference dataset."})
    try:
        raw = storage.read(asset.s3_uri)
    except Exception as exc:
        raise ValidationError({"reference_data": "Could not read reference data from storage."}) from exc

    return parse_reference_preview(raw, asset.name, max_rows=100)

