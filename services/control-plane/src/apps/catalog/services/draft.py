import os
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import DraftAsset, DraftAssetUpload, DraftRevisionAsset, ModelDraft, ModelDraftRevision
from apps.catalog.services.archive_validation import validate_tar_archive, validate_zip_archive
from apps.deployment.models import Build, BuildInputAsset, Deployment
from apps.deployment.tasks import execute_build
from apps.registry.models import ModelVersion, RegistryAlias
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import (
    build_input_prefix,
    draft_asset_key,
)


def ensure_project_draft(*, project):
    """Ensure a ModelDraft exists for the given project and return it."""
    draft, _ = ModelDraft.objects.get_or_create(project=project)
    return draft


def get_project_overview(*, project):
    """Aggregate project metadata, present production version, draft workspace, and candidate versions."""
    # 1. Present representation (production alias)
    alias = (
        RegistryAlias.objects.filter(project=project, name="production")
        .select_related("version", "version__reference_snapshot")
        .first()
    )
    present_data = None
    if alias:
        version = alias.version
        deployment = (
            Deployment.objects.filter(version=version, target="production")
            .select_related("endpoint")
            .order_by("-created_at")
            .first()
        )
        active_endpoint = getattr(deployment, "endpoint", None)
        is_live = bool(deployment and deployment.status == "healthy" and active_endpoint and active_endpoint.health_status == "healthy")
        if is_live:
            health_status = "healthy"
        elif deployment and deployment.status in {"pending", "deploying"}:
            health_status = "deploying"
        elif deployment and deployment.status == "stopped":
            health_status = "stopped"
        elif deployment and deployment.status in {"unhealthy", "failed"}:
            health_status = "unhealthy"
        else:
            health_status = "unavailable"
        image_uri = version.artifacts.filter(kind="image").values_list("uri", flat=True).first() or ""

        ref_snapshot = None
        if version.reference_snapshot:
            snap = version.reference_snapshot
            ref_snapshot = {
                "id": str(snap.public_id),
                "role": snap.role,
                "manifest_uri": snap.manifest_uri,
                "manifest_checksum": snap.manifest_checksum,
                "schema_checksum": snap.schema_checksum,
                "row_count": snap.row_count,
            }

        present_data = {
            "has_production": True,
            "is_live": is_live,
            "version": version.version,
            "version_id": str(version.public_id),
            "image_uri": image_uri,
            "endpoint_url": active_endpoint.public_url if active_endpoint else None,
            "health_status": health_status,
            "reference_snapshot": ref_snapshot,
            "metrics": version.metrics_summary,
        }
    else:
        present_data = {
            "has_production": False,
            "is_live": False,
            "version": None,
            "version_id": None,
            "image_uri": "",
            "endpoint_url": None,
            "health_status": "unavailable",
            "reference_snapshot": None,
            "metrics": {},
        }

    # 2. Draft workspace
    draft = project.current_draft
    assets = [
        {
            "id": str(asset.public_id),
            "kind": asset.kind,
            "name": asset.name,
            "size_bytes": asset.size_bytes,
            "checksum": asset.checksum,
            "content_type": asset.content_type,
            "download_url": S3Storage().presigned_get(asset.s3_uri, 900),
            "created_at": asset.created_at,
            "updated_at": asset.updated_at,
        }
        for asset in draft.assets.all()
    ]
    draft_data = {
        "id": str(draft.public_id),
        "status": draft.status,
        "revision": draft.revision,
        "saved_revision": draft.saved_revision,
        "flavor": draft.flavor,
        "artifact_format": draft.artifact_format,
        "requirements_snapshot": draft.requirements_snapshot,
        "locked_by_build_id": str(draft.locked_by_build.public_id) if draft.locked_by_build else None,
        "saved_at": draft.saved_at,
        "is_dirty": draft.is_dirty,
        "has_mandatory_assets": draft.has_mandatory_assets(),
        "can_build": draft.can_build(),
        "assets": assets,
    }

    # 3. Candidate versions (recent versions)
    recent_versions = project.versions.order_by("-registered_at")[:5]
    candidates_data = [
        {
            "id": str(v.public_id),
            "version": v.version,
            "registered_at": v.registered_at,
            "aliases": list(v.aliases.values_list("name", flat=True)),
        }
        for v in recent_versions
    ]

    return {
        "project": {
            "id": str(project.public_id),
            "name": project.name,
            "description": project.description,
            "task_domain": project.task_domain,
            "access_mode": project.access_mode,
            "lifecycle_status": project.lifecycle_status,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        },
        "present": present_data,
        "draft": draft_data,
        "candidate_versions": candidates_data,
    }


def save_draft(*, draft, expected_revision, storage=None):
    """Create an immutable asset snapshot, then atomically publish the new revision."""
    storage = storage or S3Storage()
    with transaction.atomic():
        draft = ModelDraft.objects.select_for_update().select_related("project", "project__owner").get(pk=draft.pk)
        if draft.status in {"locked", "saving"}:
            raise ValidationError({"draft": "Draft cannot be saved while locked or already saving."})
        if draft.revision != expected_revision:
            raise Conflict(f"Draft revision mismatch. Expected {expected_revision}; current is {draft.revision}.")
        if not draft.has_mandatory_assets():
            raise ValidationError({"draft": "Mandatory assets (model and reference_data) are required before saving."})
        draft.status = "saving"
        draft.save(update_fields=["status", "updated_at"])
        project, revision_number = draft.project, draft.revision

    revision_id = uuid.uuid4()
    prefix = f"users/{project.owner.tenant_id}/models/{project.public_id}/draft/revisions/{revision_id}/"
    copied = []
    try:
        working_assets = list(draft.assets.all())
        for asset in working_assets:
            key = f"{prefix}{asset.kind}/{Path(asset.name).name}"
            saved = storage.copy(asset.s3_uri, key)
            copied.append((asset, saved))
        with transaction.atomic():
            locked = ModelDraft.objects.select_for_update().get(pk=draft.pk)
            if locked.revision != expected_revision or locked.status != "saving":
                raise Conflict("Draft changed while its immutable snapshot was being saved.")
            revision = ModelDraftRevision.objects.create(
                public_id=revision_id,
                draft=locked,
                number=revision_number,
                flavor=locked.flavor,
                artifact_format=locked.artifact_format,
                requirements_snapshot=locked.requirements_snapshot,
                source_version=locked.source_version,
            )
            DraftRevisionAsset.objects.bulk_create([
                DraftRevisionAsset(
                    revision=revision,
                    kind=asset.kind,
                    name=asset.name,
                    uri=saved.uri,
                    checksum=saved.checksum or asset.checksum,
                    size_bytes=saved.size_bytes or asset.size_bytes,
                    content_type=saved.content_type or asset.content_type,
                    metadata=asset.metadata,
                ) for asset, saved in copied
            ])
            locked.saved_snapshot = revision
            locked.saved_revision = locked.revision
            locked.saved_at = timezone.now()
            locked.status = "ready"
            locked.save(update_fields=["saved_snapshot", "saved_revision", "saved_at", "status", "updated_at"])
            return locked
    except Exception:
        storage.delete_prefix(prefix)
        ModelDraft.objects.filter(pk=draft.pk, status="saving").update(status="editing")
        raise


def discard_draft(*, draft, storage=None):
    storage = storage or S3Storage()
    with transaction.atomic():
        locked = ModelDraft.objects.select_for_update().select_related("saved_snapshot").get(pk=draft.pk)
        if locked.status in {"locked", "saving"}:
            raise ValidationError({"draft": "Cannot discard a locked or saving draft."})
        snapshot = locked.saved_snapshot
        current_uris = list(locked.assets.values_list("s3_uri", flat=True))
        if snapshot:
            assets = list(snapshot.assets.all())
            locked.flavor = snapshot.flavor
            locked.artifact_format = snapshot.artifact_format
            locked.requirements_snapshot = snapshot.requirements_snapshot
            locked.source_version = snapshot.source_version
            locked.assets.all().delete()
            DraftAsset.objects.bulk_create([
                DraftAsset(draft=locked, kind=item.kind, name=item.name, s3_uri=item.uri, checksum=item.checksum,
                           size_bytes=item.size_bytes, content_type=item.content_type, metadata=item.metadata)
                for item in assets
            ])
            locked.saved_revision = locked.revision + 1
            locked.status = "ready"
        else:
            locked.assets.all().delete()
            locked.flavor = ""
            locked.artifact_format = "raw"
            locked.requirements_snapshot = ""
            locked.source_version = None
            locked.saved_revision = 0
            locked.status = "editing"
        locked.revision += 1
        locked.saved_at = timezone.now() if snapshot else None
        locked.save(update_fields=["flavor", "artifact_format", "requirements_snapshot", "source_version", "revision", "saved_revision", "saved_at", "status", "updated_at"])
    retained = set(locked.assets.values_list("s3_uri", flat=True))
    for uri in current_uris:
        if uri not in retained:
            try:
                storage.delete(uri)
            except Exception:
                pass
    return locked


def create_draft_asset_upload_url(
    *, draft, user, kind, filename, content_type="application/octet-stream", size_bytes=0, checksum="", storage=None
):
    """Generate a presigned S3 PUT URL for uploading a draft asset."""
    storage = storage or S3Storage()
    valid_kinds = {k[0] for k in DraftAsset.KINDS}
    if kind not in valid_kinds:
        raise ValidationError({"kind": f"Unsupported draft asset kind: {kind}"})

    if draft.status == "locked":
        raise ValidationError({"draft": "Cannot upload assets while draft is locked by an ongoing build."})

    safe_filename = Path(filename).name
    if not safe_filename or safe_filename in {".", ".."}:
        raise ValidationError({"filename": "Invalid filename."})

    if size_bytes <= 0 or size_bytes > 2 * 1024**3:
        raise ValidationError({"size_bytes": "Upload size must be between 1 byte and 2 GiB."})
    if not checksum or len(checksum) != 64:
        raise ValidationError({"checksum": "A SHA-256 hex digest is required."})
    suffix = Path(safe_filename).suffix.lower()
    extensions = {
        "model": {".pkl", ".joblib", ".json", ".ubj", ".pt", ".pth", ".h5", ".keras", ".onnx", ".zip", ".tar", ".gz"},
        "reference_data": {".csv", ".parquet", ".json", ".jsonl", ".zip", ".gz"},
        "source_code": {".zip"},
        "label_mapping": {".json", ".csv"},
        "data_contract": {".json", ".yaml", ".yml"},
        "metrics": {".json", ".csv"},
        "params": {".json", ".yaml", ".yml"},
        "model_insights": {".json"},
        "feature_importance": {".json", ".csv"},
        "input_schema": {".json", ".yaml", ".yml"},
    }
    if suffix not in extensions.get(kind, set()):
        raise ValidationError({"filename": f"Unsupported file extension for {kind}."})
    upload_id = uuid.uuid4()
    key = draft_asset_key(
        draft.project.owner.tenant_id,
        draft.project.public_id,
        draft.public_id,
        kind,
        f"{upload_id}-{safe_filename}",
    )
    s3_uri = f"s3://{storage.bucket}/{key}"
    session = DraftAssetUpload.objects.create(
        public_id=upload_id, draft=draft, user=user, kind=kind, object_key=key, filename=safe_filename,
        size_bytes=size_bytes, checksum=checksum.lower(), content_type=content_type,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    upload_url = storage.presigned_put(s3_uri, expires_in=900, content_type=content_type, metadata={"sha256": checksum.lower()})
    return {
        "upload_url": upload_url,
        "upload_id": str(session.public_id),
        "headers": {"Content-Type": content_type, "x-amz-meta-sha256": checksum.lower()},
        "expires_in": 900,
        "kind": kind,
        "filename": safe_filename,
    }


def complete_draft_asset_upload(*, draft, user, upload_id, storage=None):
    """Verify S3 upload completion, perform archive safety checks, register DraftAsset, and increment revision."""
    storage = storage or S3Storage()
    with transaction.atomic():
        draft = ModelDraft.objects.select_for_update().get(pk=draft.pk)
        if draft.status in {"locked", "saving"}:
            raise ValidationError({"draft": "Cannot complete upload while draft is locked."})
        session = DraftAssetUpload.objects.select_for_update().filter(
            public_id=upload_id, draft=draft, user=user, completed_at__isnull=True
        ).first()
        if not session or session.expires_at <= timezone.now():
            raise ValidationError({"upload_id": "Upload session is invalid, expired, or already used."})
        s3_uri = f"s3://{storage.bucket}/{session.object_key}"
        try:
            head_meta = storage.head(s3_uri)
            actual_size = head_meta.get("ContentLength", 0)
        except Exception as exc:
            raise ValidationError({"upload_id": f"Uploaded object could not be verified: {str(exc)}"}) from exc
        actual_checksum = head_meta.get("Metadata", {}).get("sha256", "").lower()
        if actual_size != session.size_bytes or actual_checksum != session.checksum:
            raise ValidationError({"upload_id": "Uploaded size or SHA-256 does not match the upload session."})

        # Archive safety validation if applicable
        safe_filename = session.filename
        is_tar = safe_filename.endswith(".tar.gz") or safe_filename.endswith(".tgz") or safe_filename.endswith(".tar")
        is_zip = safe_filename.endswith(".zip")
        if is_tar or is_zip:
            with tempfile.NamedTemporaryFile(suffix=safe_filename, delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)
            try:
                storage.download_file(s3_uri, tmp_path)
                if is_tar:
                    validate_tar_archive(str(tmp_path))
                elif is_zip:
                    validate_zip_archive(str(tmp_path))
            finally:
                if tmp_path.exists():
                    os.unlink(tmp_path)

        asset, _ = DraftAsset.objects.update_or_create(
            draft=draft,
            kind=session.kind,
            defaults={
                "name": safe_filename,
                "s3_uri": s3_uri,
                "size_bytes": actual_size,
                "checksum": session.checksum,
                "content_type": session.content_type,
            },
        )
        session.completed_at = timezone.now()
        session.save(update_fields=["completed_at"])
        draft.revision += 1
        draft.save(update_fields=["revision", "updated_at"])
        return asset


def delete_draft_asset(*, draft, kind, storage=None):
    """Remove an asset from the draft and its S3 object, incrementing revision."""
    storage = storage or S3Storage()
    with transaction.atomic():
        draft = ModelDraft.objects.select_for_update().get(pk=draft.pk)
        if draft.status == "locked":
            raise ValidationError({"draft": "Cannot delete asset while draft is locked."})

        asset = draft.assets.filter(kind=kind).first()
        if not asset:
            return False

        try:
            storage.delete(asset.s3_uri)
        except Exception:
            pass

        asset.delete()
        draft.revision += 1
        if draft.status == "ready":
            draft.status = "editing"
        draft.save(update_fields=["revision", "status", "updated_at"])
        return True


def dispatch_draft_build(*, draft, actor, backend="docker", storage=None):
    """Validate readiness, snapshot all draft assets to build inputs, lock draft, and trigger Celery task."""
    storage = storage or S3Storage()
    with transaction.atomic():
        draft = ModelDraft.objects.select_for_update().select_related("project", "project__owner").get(pk=draft.pk)
        if draft.status == "locked":
            raise ValidationError({"draft": "Draft is currently locked by an ongoing build."})

        if not draft.has_mandatory_assets() or not draft.saved_snapshot_id:
            raise ValidationError(
                {"draft": "Cannot build: missing mandatory assets (model and reference_data are required)."}
            )

        if draft.is_dirty:
            raise ValidationError(
                {"draft": "Cannot build: there are unsaved changes in the draft. Please save the draft first."}
            )

        project = draft.project
        build = Build.objects.create(
            project=project,
            source_draft_revision=draft.saved_snapshot,
            flavor=draft.flavor or "sklearn",
            artifact_format=draft.artifact_format,
            requirements_snapshot=draft.requirements_snapshot,
            backend=backend,
            status="pending",
        )

        # Snapshot every DraftAsset into BuildInputAsset
        for asset in draft.saved_snapshot.assets.all():
            dest_prefix = build_input_prefix(
                project.owner.tenant_id,
                project.public_id,
                build.public_id,
                asset.kind,
            )
            dest_key = f"{dest_prefix}{asset.name}"
            stored = storage.copy(asset.uri, dest_key)
            BuildInputAsset.objects.create(
                build=build,
                kind=asset.kind,
                name=asset.name,
                s3_uri=stored.uri,
                checksum=stored.checksum or asset.checksum,
                size_bytes=stored.size_bytes or asset.size_bytes,
                content_type=stored.content_type or asset.content_type,
            )

        # Lock draft
        draft.status = "locked"
        draft.locked_by_build = build
        draft.save(update_fields=["status", "locked_by_build", "updated_at"])

        transaction.on_commit(lambda: execute_build.delay(str(build.public_id)))
        return build


def load_version_into_draft(*, draft, version_id, confirm=False, storage=None):
    """Copy all snapshot assets and metadata from an immutable ModelVersion into the Draft."""
    if not confirm:
        raise ValidationError(
            {
                "confirm": "Confirmation required. Loading a version will overwrite current draft contents. Pass confirm=true to proceed."
            }
        )

    storage = storage or S3Storage()
    copied = []
    with transaction.atomic():
        draft = ModelDraft.objects.select_for_update().select_related("project", "project__owner").get(pk=draft.pk)
        if draft.status == "locked":
            raise ValidationError(
                {"draft": "Cannot load version into draft while draft is locked by an ongoing build."}
            )

        project = draft.project
        try:
            version = ModelVersion.objects.prefetch_related("artifacts").get(project=project, public_id=version_id)
        except ModelVersion.DoesNotExist:
            raise ValidationError({"version_id": "Version not found in this project."})

        # Copy version artifacts into DraftAssets
        for artifact in version.artifacts.all():
            # Map version artifact kind to draft kind
            draft_kind = artifact.kind
            if draft_kind not in {k[0] for k in DraftAsset.KINDS}:
                continue

            dest_key = draft_asset_key(
                project.owner.tenant_id,
                project.public_id,
                draft.public_id,
                draft_kind,
                f"{uuid.uuid4()}-{Path(artifact.name).name}",
            )
            stored = storage.copy(artifact.uri, dest_key)
            copied.append((draft_kind, artifact, stored))

        if not any(kind == "reference_data" for kind, _, _ in copied) or not any(kind == "model" for kind, _, _ in copied):
            raise ValidationError({"version_id": "Version must include model and reference_data artifacts."})
        old_uris = list(draft.assets.values_list("s3_uri", flat=True))
        draft.assets.all().delete()
        DraftAsset.objects.bulk_create([
            DraftAsset(draft=draft, kind=kind, name=artifact.name, s3_uri=stored.uri,
                       checksum=stored.checksum or artifact.checksum, size_bytes=stored.size_bytes or artifact.size_bytes,
                       content_type=stored.content_type or artifact.content_type)
            for kind, artifact, stored in copied
        ])

        draft.flavor = version.flavor
        draft.requirements_snapshot = version.requirements_snapshot
        draft.source_version = version
        draft.revision += 1
        draft.saved_revision = 0
        draft.saved_snapshot = None
        draft.saved_at = None
        draft.status = "editing"
        draft.save(update_fields=["flavor", "requirements_snapshot", "source_version", "revision", "saved_revision", "saved_snapshot", "saved_at", "status", "updated_at"])
    for uri in old_uris:
        try:
            storage.delete(uri)
        except Exception:
            pass
    return draft
