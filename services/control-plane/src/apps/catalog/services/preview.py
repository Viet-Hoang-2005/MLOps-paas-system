"""Revision-checked drafts and immutable build inputs."""

import hashlib
import json
import uuid
from pathlib import Path

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.artifact_types import (
    validate_source_artifact,
)
from apps.catalog.models import ModelPreview, PreviewAsset
from apps.catalog.services.snapshots import parse_label_mapping_payload
from common.api.exceptions import Conflict
from common.validation.artifacts import (
    MAX_REFERENCE_DATA_BYTES,
    MAX_SOURCE_CODE_BYTES,
    parse_reference_preview,
    validate_reference_data_content,
    validate_source_code_content,
)
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import project_prefix

def generate_preview_upload_urls(
    *, tenant_id, project_id, files_data, storage=None, flavor=None, artifact_format="raw"
):
    storage = storage or S3Storage()
    upload_batch_id = uuid.uuid4()
    result = []
    for item in files_data:
        kind = item["kind"]
        filename = Path(item["filename"].replace("\\", "/")).name
        if not filename or filename in {".", ".."}:
            raise ValidationError({kind: "Invalid filename."})
        size_bytes = item.get("size_bytes")
        if size_bytes is None or size_bytes <= 0:
            raise ValidationError({kind: "File size (size_bytes) must be greater than 0."})

        if kind == "source_artifact":
            if not flavor:
                raise ValidationError({"flavor": "Flavor must be specified."})
            validate_source_artifact(
                filename=filename,
                flavor=flavor,
                artifact_format=artifact_format,
                size_bytes=size_bytes,
            )
        elif kind == "source_code":
            if not filename.lower().endswith(".py"):
                raise ValidationError({"source_code": "Source code must be a Python (.py) file."})
            if size_bytes > MAX_SOURCE_CODE_BYTES:
                raise ValidationError(
                    {"source_code": f"Source code file must be at most {MAX_SOURCE_CODE_BYTES // (1024 * 1024)} MiB."}
                )
        elif kind == "reference_data":
            if not filename.lower().endswith(".csv"):
                raise ValidationError({"reference_data": "Reference dataset must be a CSV (.csv) file."})
            if size_bytes > MAX_REFERENCE_DATA_BYTES:
                raise ValidationError(
                    {"reference_data": f"Reference data file must be at most {MAX_REFERENCE_DATA_BYTES // (1024 * 1024)} MiB."}
                )
        elif kind == "label_mapping":
            if Path(filename).suffix.lower() != ".json":
                raise ValidationError({"label_mapping": "Label mapping must be a .json file."})
            if size_bytes > 4 * 1024 * 1024:
                raise ValidationError({"label_mapping": "Upload a valid JSON file under 4 MiB."})
        elif kind in {"metrics", "params", "model_insights", "feature_importance", "input_schema"}:
            if not filename.lower().endswith(".json"):
                raise ValidationError({kind: "Upload a JSON file."})
            if size_bytes > 4 * 1024 * 1024:
                raise ValidationError({kind: "Upload a valid JSON file under 4 MiB."})

        # Presigned upload URLs target strictly an ephemeral staging area.
        # Upon preview save, valid staged files are promoted (copied) to an immutable committed key,
        # ensuring the presigned URL cannot be used to overwrite committed preview assets.
        # Ephemeral staging keys start with 'staging/' prefix so S3 Lifecycle rules can automatically
        # purge uncommitted or abandoned uploads.
        key = f"staging/{project_prefix(tenant_id, project_id)}/preview/{upload_batch_id}/{kind}/{filename}"
        s3_uri = f"s3://{storage.bucket}/{key}"
        content_type = item.get("content_type") or "application/octet-stream"
        upload_url = storage.presigned_put(
            s3_uri, expires_in=900, content_type=content_type, size_bytes=size_bytes
        )
        result.append(
            {
                "kind": kind,
                "filename": filename,
                "s3_uri": s3_uri,
                "upload_url": upload_url,
                "content_type": content_type,
            }
        )
    return result


def save_preview(*, project, data, storage=None, require_artifact=False):
    storage = storage or S3Storage()
    if any(data.get(f"{kind}_file") for kind, _ in PreviewAsset.KINDS):
        raise ValidationError({"assets": "Upload files with a presigned staging URL."})
    presigned_assets = data.get("assets") or []

    # Path 1: Presigned S3 Assets flow (when presigned_assets list is provided and non-empty)
    if presigned_assets:
        tenant_id = project.owner.tenant_id
        project_id = str(project.public_id)
        expected_staging_prefix = f"s3://{storage.bucket}/staging/{project_prefix(tenant_id, project_id)}/preview/"

        # Collect candidate staging URIs strictly confined to this project's staging prefix
        # for cleanup if save_preview fails at any stage.
        staged_uris_to_clean = [
            item["s3_uri"]
            for item in presigned_assets
            if isinstance(item, dict)
            and isinstance(item.get("s3_uri"), str)
            and item["s3_uri"].startswith(expected_staging_prefix)
        ]

        # Query database directly for current flavor/format to avoid stale in-memory cached attributes
        current_preview = ModelPreview.objects.filter(project=project).first()
        flavor = data.get("flavor") or (current_preview.flavor if current_preview else "")
        artifact_format = data.get("artifact_format") or (current_preview.artifact_format if current_preview else "raw")
        remove = set(data.get("remove_assets", []))

        committed_assets = []
        committed_uris = []
        try:
            # 1. Pre-transaction validation and S3 head checks OUTSIDE DB lock
            verified_staging_assets = []
            for item in presigned_assets:
                kind = item["kind"]
                name = Path(item["name"].replace("\\", "/")).name
                s3_uri = item["s3_uri"]
                # Enforce that uploaded asset must come strictly from the staging prefix
                if not s3_uri.startswith(expected_staging_prefix):
                    raise ValidationError({"assets": f"Storage URI for '{kind}' does not belong to this project's preview staging area."})

                try:
                    stored = storage.head(s3_uri)
                except Exception as exc:
                    raise ValidationError({"assets": f"Could not verify uploaded asset '{kind}' in storage: {exc}"}) from exc

                if stored.size_bytes == 0:
                    raise ValidationError({"assets": f"Uploaded asset '{kind}' is empty."})
                if not stored.etag:
                    raise ValidationError({"assets": f"Uploaded asset '{kind}' has no storage ETag."})

                checksum = ""
                if kind == "source_artifact":
                    if not flavor:
                        raise ValidationError({"flavor": "Flavor must be specified."})
                    validate_source_artifact(
                        filename=name,
                        flavor=flavor,
                        artifact_format=artifact_format,
                        size_bytes=stored.size_bytes,
                    )
                    # For model artifacts (can be multi-GB), do NOT stream over network in web request.
                    # Use client-provided checksum, storage metadata checksum, or fallback to ETag.
                    checksum = item.get("checksum") or stored.checksum or stored.etag.strip('"')
                elif kind == "source_code":
                    if not name.lower().endswith(".py"):
                        raise ValidationError({"source_code": "Source code must be a Python (.py) file."})
                    if stored.size_bytes > MAX_SOURCE_CODE_BYTES:
                        raise ValidationError(
                            {"source_code": f"Source code file must be at most {MAX_SOURCE_CODE_BYTES // (1024 * 1024)} MiB."}
                        )
                    content = storage.read(s3_uri, max_bytes=MAX_SOURCE_CODE_BYTES + 1)
                    validate_source_code_content(name, content, error_key="source_code")
                    checksum = hashlib.sha256(content).hexdigest()
                elif kind == "reference_data":
                    if not name.lower().endswith(".csv"):
                        raise ValidationError({"reference_data": "Reference dataset must be a CSV (.csv) file."})
                    if stored.size_bytes > MAX_REFERENCE_DATA_BYTES:
                        raise ValidationError(
                            {"reference_data": f"Reference data file must be at most {MAX_REFERENCE_DATA_BYTES // (1024 * 1024)} MiB."}
                        )
                    content = storage.read(s3_uri, max_bytes=MAX_REFERENCE_DATA_BYTES + 1)
                    validate_reference_data_content(name, content, error_key="reference_data")
                    checksum = hashlib.sha256(content).hexdigest()
                elif kind in {"label_mapping", "metrics", "params", "model_insights", "feature_importance", "input_schema"}:
                    if not name.lower().endswith(".json"):
                        raise ValidationError({kind: "Upload a JSON file."})
                    if stored.size_bytes > 4 * 1024 * 1024:
                        raise ValidationError({kind: "Upload a valid JSON file under 4 MiB."})
                    try:
                        content = storage.read(s3_uri, max_bytes=4 * 1024 * 1024 + 1)
                        if len(content) > 4 * 1024 * 1024:
                            raise ValueError
                        if kind == "label_mapping":
                            value = parse_label_mapping_payload(name, content)
                        else:
                            value = json.loads(content)
                            if not isinstance(value, (dict, list)):
                                raise ValueError
                            if kind in {"metrics", "params", "model_insights", "input_schema"} and not isinstance(value, dict):
                                raise ValueError
                    except Exception as exc:
                        if isinstance(exc, ValidationError):
                            raise
                        raise ValidationError({kind: "Upload a valid JSON file under 4 MiB."}) from exc
                    checksum = hashlib.sha256(content).hexdigest()

                verified_staging_assets.append(
                    (kind, name, s3_uri, checksum, stored.size_bytes, stored.content_type, stored.etag)
                )

            # Validate effective artifact (newly uploaded or retained existing) against final flavor & format
            new_artifact_item = next(
                ((name, size) for k, name, _, _, size, *_ in verified_staging_assets if k == "source_artifact"),
                None,
            )
            existing_artifact = current_preview.assets.filter(kind="source_artifact").first() if current_preview else None
            effective_artifact_name = (
                new_artifact_item[0]
                if new_artifact_item
                else (existing_artifact.name if existing_artifact and "source_artifact" not in remove else None)
            )
            effective_artifact_size = (
                new_artifact_item[1]
                if new_artifact_item
                else (existing_artifact.size_bytes if existing_artifact and "source_artifact" not in remove else None)
            )
            if effective_artifact_name:
                if not flavor:
                    raise ValidationError({"flavor": "Flavor must be specified."})
                validate_source_artifact(
                    filename=effective_artifact_name,
                    flavor=flavor,
                    artifact_format=artifact_format,
                    size_bytes=effective_artifact_size,
                )
            elif require_artifact:
                raise ValidationError({"source_artifact": "A model artifact is required."})

            # 2. Promote / Commit staging assets to immutable committed destination keys.
            # Crucial for data integrity (P1): Once saved, the preview asset points to a committed key
            # that has NEVER had a presigned PUT URL issued for it. Any post-save reuse of the presigned
            # URL only affects the abandoned staging key and CANNOT overwrite the saved preview object.
            for kind, name, staging_uri, staging_checksum, staging_size, staging_content_type, staging_etag in verified_staging_assets:
                commit_token = uuid.uuid4()
                committed_key = (
                    f"{project_prefix(tenant_id, project_id)}/preview/committed/{commit_token}/{kind}/{name}"
                )
                stored_committed = storage.copy(
                    staging_uri,
                    committed_key,
                    checksum=staging_checksum,
                    content_type=staging_content_type,
                    size_bytes=staging_size,
                    expected_etag=staging_etag,
                )
                committed_uris.append(stored_committed.uri)
                committed_assets.append((kind, name, stored_committed))

            # 3. Fast atomic database transaction (<10ms)
            with transaction.atomic():
                project = type(project).objects.select_for_update().get(pk=project.pk)
                if not project.is_active or project.deletion_state != "active":
                    raise Conflict("This project is being deleted.")
                preview = ModelPreview.objects.select_for_update().get(project=project)
                if data.get("revision") is not None and data.get("revision") != preview.revision:
                    raise Conflict("Preview changed in another session. Reload before saving.")

                # If replacing existing assets of the same kind, clean up old committed S3 objects
                replaced_kinds = {kind for kind, _, _ in committed_assets}
                old_assets_to_delete = list(preview.assets.filter(kind__in=replaced_kinds | remove))
                old_uris = [a.s3_uri for a in old_assets_to_delete if a.s3_uri]

                for kind, name, stored in committed_assets:
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
                if remove:
                    preview.assets.filter(kind__in=remove - replaced_kinds).delete()
                preview.flavor = flavor or preview.flavor
                preview.artifact_format = artifact_format or preview.artifact_format
                preview.requirements_text = data.get("requirements_text", preview.requirements_text)
                preview.revision += 1
                preview.save()

            for uri in old_uris + staged_uris_to_clean:
                try:
                    storage.delete(uri)
                except Exception:
                    pass
            return preview
        except Exception:
            for uri in committed_uris:
                try:
                    storage.delete(uri)
                except Exception:
                    pass
            raise

    # Metadata-only update.
    with transaction.atomic():
        project = type(project).objects.select_for_update().get(pk=project.pk)
        if not project.is_active or project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        preview = ModelPreview.objects.select_for_update().get(project=project)
        if data.get("revision") is not None and data.get("revision") != preview.revision:
            raise Conflict("Preview changed in another session. Reload before saving.")
        flavor = data.get("flavor", preview.flavor)
        artifact_format = data.get("artifact_format", preview.artifact_format)
        remove = set(data.get("remove_assets", []))
        existing = preview.assets.filter(kind="source_artifact").first()
        if existing and "source_artifact" not in remove:
            validate_source_artifact(
                filename=existing.name,
                flavor=flavor,
                artifact_format=artifact_format,
                size_bytes=existing.size_bytes,
            )
        elif require_artifact:
            raise ValidationError({"source_artifact": "A model artifact is required."})
        preview.assets.filter(kind__in=remove).delete()
        preview.flavor = flavor
        preview.artifact_format = artifact_format
        preview.requirements_text = data.get("requirements_text", preview.requirements_text)
        preview.revision += 1
        preview.save()
    return preview


def create_project_preview(*, actor, data, storage=None):
    from apps.catalog.services.project_metadata import save_project_metadata

    project = save_project_metadata(
        actor=actor,
        validated_data={key: data[key] for key in ("name", "description", "access_mode", "project_id") if key in data},
    )
    try:
        save_preview(
            project=project,
            data={**data, "revision": project.preview.revision},
            storage=storage,
            require_artifact=True,
        )
        project.refresh_from_db()
        return project
    except Exception:
        project.delete()
        raise


def get_preview_reference_preview(project, storage=None) -> dict:
    storage = storage or S3Storage()
    preview = project.preview
    asset = preview.assets.filter(kind="reference_data").first()
    if not asset or not asset.s3_uri:
        raise ValidationError({"reference_data": "This project preview does not have a reference dataset."})
    try:
        raw = storage.read(asset.s3_uri, max_bytes=MAX_REFERENCE_DATA_BYTES)
    except Exception as exc:
        raise ValidationError({"reference_data": "Could not read reference data from storage."}) from exc

    return parse_reference_preview(raw, asset.name, max_rows=100)
