"""Account-owned training drafts. Object keys never depend on editable paths."""

import json
import hashlib
import re
import uuid
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.training.models import TrainingJob, TrainingJobEntry, TrainingJobSecret
from common.api.exceptions import Conflict, ServiceUnavailable
from common.validation.artifacts import validate_reference_data_content
from infrastructure.storage import S3Storage

EXTENSIONS = {"script": ".py", "data": ".csv", "config": ".json", "document": ".md", "requirements": ".txt"}
MAX_TEXT = 5 * 1024 * 1024
MAX_DATA = 100 * 1024 * 1024
MAX_WORKSPACE_SNAPSHOT = 256 * 1024 * 1024
MAX_WORKSPACE_ENTRIES = 10_000
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
RESERVED_ENV = {"PATH", "PYTHONPATH", "PYTHONHOME", "HOME", "LD_PRELOAD", "LD_LIBRARY_PATH", "TMPDIR", "MODEL_VERSION", "INPUT_CONTRACT", "PREPARED_INPUT_DIR", "RUNTIME_CONFIG_URL", "RUNTIME_CONFIG_CAPABILITY"}
RESERVED_PREFIXES = ("MLOPS_", "SM_", "AWS_", "S3_", "REDIS_", "DJANGO_", "MLFLOW_", "TRAINING_")


def safe_path(value):
    if (not isinstance(value, str) or not value or len(value) > 512 or "\\" in value
            or value.startswith("/") or any(ord(ch) < 32 for ch in value)):
        raise ValidationError({"path": "Use a safe relative path."})
    parts = value.split("/")
    if any(not part or part in {".", ".."} or len(part) > 255 for part in parts):
        raise ValidationError({"path": "Use a safe relative path."})
    if any(part.lower() == ".env" for part in parts):
        raise ValidationError({"path": "Use Environment and Secrets instead of .env files."})
    return value


def validate_name(name):
    if (not isinstance(name, str) or not ENV_NAME.fullmatch(name) or name in RESERVED_ENV
            or name.startswith(RESERVED_PREFIXES)):
        raise ValidationError({"name": "Invalid or reserved environment variable name."})
    return name


def validate_file(path, kind, payload):
    safe_path(path)
    if kind not in EXTENSIONS:
        raise ValidationError({"kind": "Unsupported file type."})
    name = PurePosixPath(path).name
    if name.lower() == "requirements.txt" and (path != "requirements.txt" or kind != "requirements"):
        raise ValidationError({"path": "requirements.txt is reserved at the Input root."})
    if kind == "requirements" and path != "requirements.txt":
        raise ValidationError({"path": "Requirements must be named requirements.txt at the Input root."})
    if not name.lower().endswith(EXTENSIONS[kind]):
        raise ValidationError({"path": "The file extension does not match its type."})
    if len(payload) > (MAX_DATA if kind == "data" else MAX_TEXT):
        raise ValidationError({"file": "File exceeds the allowed size."})
    if kind == "data":
        validate_reference_data_content(name, payload, error_key="file")
        return
    try:
        decoded = payload.decode("utf-8")
        if "\x00" in decoded:
            raise ValueError("NUL")
        if kind == "config" and decoded.strip():
            json.loads(decoded)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValidationError({"file": "File content is not valid text or JSON."}) from exc


def _lock(workspace, revision, *, preparing=False, terminal_secret=False):
    row = TrainingJob.objects.select_for_update().get(pk=workspace.pk)
    valid_type = (isinstance(revision, int) and not isinstance(revision, bool)) or (
        isinstance(revision, str) and revision.isascii() and revision.isdecimal() and len(revision) <= 10
    )
    valid = valid_type and int(revision) == row.revision
    if not valid:
        raise Conflict("Workspace changed. Reload before saving.")
    allowed = {"pending"} if preparing else {"editing"}
    if terminal_secret:
        allowed |= {"completed", "failed", "cancelled"}
    if row.status not in allowed or row.deletion_requested_at:
        raise Conflict("This job workspace is read-only.")
    return row


def _bump(workspace):
    workspace.revision += 1
    workspace.save(update_fields=["revision", "entry_point", "environment", "updated_at"])


def _parent_exists(workspace, path):
    parent = str(PurePosixPath(path).parent)
    if parent != "." and not workspace.entries.filter(relative_path=parent, kind="folder").exists():
        raise ValidationError({"path": "Parent folder does not exist."})


def snapshot_input(workspace, *, revision, storage=None, preparing=False):
    """Build a revision-checked Input archive without holding a DB lock during I/O.

    This prepares the immutable input contract; dispatch must separately verify
    the revision again before committing a run.
    """
    with transaction.atomic():
        locked = _lock(workspace, revision, preparing=preparing)
        entries = list(locked.entries.order_by("relative_path"))
        if len(entries) > MAX_WORKSPACE_ENTRIES:
            raise ValidationError({"file": "Workspace contains too many entries."})
        entry_point = locked.entry_point
        snapshot_revision = locked.revision
        tenant_id = locked.owner.tenant_id
        workspace_id = locked.public_id
        if not entry_point or not any(e.relative_path == entry_point and e.kind == "script" for e in entries):
            raise ValidationError({"entry_point": "Select a Python entry point before running training."})

    storage = storage or S3Storage()
    prefix = f"users/{tenant_id}/training/jobs/{workspace_id}/draft/objects/"
    total = 0
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for entry in entries:
            path = safe_path(entry.relative_path)
            if entry.kind == "folder":
                archive.writestr(path + "/", b"")
                continue
            bucket, key = storage.parse_uri(entry.s3_uri)
            if bucket != storage.bucket or not key.startswith(prefix):
                raise ValidationError({"file": "Workspace file is outside its storage scope."})
            max_size = MAX_DATA if entry.kind == "data" else MAX_TEXT
            if entry.size_bytes > max_size or total + entry.size_bytes > MAX_WORKSPACE_SNAPSHOT:
                raise ValidationError({"file": "Workspace exceeds the allowed snapshot size."})
            try:
                payload = storage.read(entry.s3_uri, max_bytes=max_size)
            except Exception as exc:
                if not TrainingJob.objects.filter(pk=workspace.pk, revision=snapshot_revision).exists():
                    raise Conflict("Workspace changed. Reload before running training.") from exc
                raise
            if len(payload) != entry.size_bytes or hashlib.sha256(payload).hexdigest() != entry.checksum:
                raise ValidationError({"file": "Workspace file failed integrity verification."})
            validate_file(path, entry.kind, payload)
            total += len(payload)
            archive.writestr(path, payload)

    if not TrainingJob.objects.filter(pk=workspace.pk, revision=snapshot_revision).exists():
        raise Conflict("Workspace changed. Reload before running training.")
    return {"archive": bundle.getvalue(), "revision": snapshot_revision, "entry_point": entry_point}


def serialize_entries(entries):
    entries = list(entries)
    storage = S3Storage() if any(entry.s3_uri for entry in entries) else None
    result = []
    for entry in entries:
        item = {"id": str(entry.public_id), "path": entry.relative_path, "kind": entry.kind,
                "size_bytes": entry.size_bytes, "updated_at": entry.updated_at.isoformat()}
        if entry.s3_uri:
            item["download_url"] = storage.presigned_get(entry.s3_uri)
        result.append(item)
    return result


def update_workspace(workspace, *, revision, changes):
    with transaction.atomic():
        locked = _lock(workspace, revision)
        if "entry_point" in changes:
            path = changes["entry_point"]
            if not isinstance(path, str):
                raise ValidationError({"entry_point": "Select a Python script in this workspace."})
            if path and not locked.entries.filter(relative_path=safe_path(path), kind="script").exists():
                raise ValidationError({"entry_point": "Select a Python script in this workspace."})
            locked.entry_point = path
        if "environment" in changes:
            environment = changes["environment"]
            if not isinstance(environment, dict) or len(environment) > 100:
                raise ValidationError({"environment": "Provide at most 100 environment variables."})
            for key, value in environment.items():
                validate_name(key)
                if not isinstance(value, str) or len(value.encode("utf-8")) > 8192:
                    raise ValidationError({"environment": "Environment values must be text up to 8192 bytes."})
            if locked.secrets.filter(name__in=environment).exists():
                raise Conflict("An environment variable conflicts with a secret name.")
            locked.environment = environment
        config_fields = {"model_flavor", "vcpu", "memory_mb", "max_runtime_seconds", "accelerator_type", "accelerator_count", "accelerator_model", "local_gpu_id"}
        for field in config_fields & changes.keys():
            setattr(locked, field, changes[field])
        _bump(locked)
        locked.save(update_fields=list(config_fields & changes.keys()) + ["updated_at"])
        return locked


def create_entry(workspace, *, revision, path, kind, payload=None, storage=None):
    safe_path(path)
    if kind == "folder":
        if payload is not None:
            raise ValidationError({"file": "Folders cannot contain uploaded content."})
        if PurePosixPath(path).name.lower() == "requirements.txt":
            raise ValidationError({"path": "requirements.txt is reserved for the requirements file."})
    else:
        if payload is None:
            if kind == "data":
                raise ValidationError({"file": "CSV upload is required."})
            payload = b""
        validate_file(path, kind, payload)
    storage = storage or S3Storage()
    stored = None
    if kind != "folder":
        key = f"users/{workspace.owner.tenant_id}/training/jobs/{workspace.public_id}/draft/objects/{uuid.uuid4().hex}"
        content_type = "text/csv" if kind == "data" else "text/plain; charset=utf-8"
        stored = storage.put(key, payload, content_type)
    try:
        with transaction.atomic():
            locked = _lock(workspace, revision)
            _parent_exists(locked, path)
            if locked.entries.filter(relative_path=path).exists():
                raise Conflict("A file or folder already exists at this path.")
            entry = TrainingJobEntry.objects.create(job=locked, relative_path=path, kind=kind,
                s3_uri=stored.uri if stored else "", checksum=stored.checksum if stored else "",
                size_bytes=stored.size_bytes if stored else 0, content_type=stored.content_type if stored else "")
            _bump(locked)
        return entry, locked.revision
    except Exception:
        if stored:
            storage.delete(stored.uri)
        raise


def edit_file(workspace, entry_id, *, revision, path=None, kind=None, payload=None, replacement=False, storage=None):
    """Atomically change a file's name, type, and optionally its contents."""
    entry = workspace.entries.get(public_id=entry_id)
    if entry.kind == "folder":
        if kind is not None or payload is not None or path is None:
            raise ValidationError("Folders can only be moved or renamed.")
        return entry, move_entry(workspace, entry_id, revision=revision, path=path)
    path = entry.relative_path if path is None else safe_path(path)
    kind = entry.kind if kind is None else kind
    if kind == "requirements" and entry.kind != "requirements":
        raise ValidationError({"kind": "Create requirements.txt as a new file."})
    if entry.kind == "requirements" and (path != "requirements.txt" or kind != "requirements" or replacement):
        raise ValidationError({"file": "Delete requirements.txt before replacing or moving it."})
    storage = storage or S3Storage()
    if payload is None:
        if path == entry.relative_path and kind == entry.kind:
            with transaction.atomic():
                locked = _lock(workspace, revision)
                entry = locked.entries.select_for_update().get(public_id=entry_id)
                return entry, locked.revision
        if kind != entry.kind:
            payload_to_validate = storage.read(entry.s3_uri, max_bytes=MAX_DATA)
            validate_file(path, kind, payload_to_validate)
        else:
            validate_file(path, kind, b"" if kind != "data" else b"column\nvalue\n")
        stored = None
    else:
        validate_file(path, kind, payload)
        key = f"users/{workspace.owner.tenant_id}/training/jobs/{workspace.public_id}/draft/objects/{uuid.uuid4().hex}"
        content_type = "text/csv" if kind == "data" else "text/plain; charset=utf-8"
        stored = storage.put(key, payload, content_type)
    try:
        with transaction.atomic():
            locked = _lock(workspace, revision)
            entry = locked.entries.select_for_update().get(public_id=entry_id)
            _parent_exists(locked, path)
            if locked.entries.filter(relative_path=path).exclude(pk=entry.pk).exists():
                raise Conflict("A file or folder already exists at this path.")
            old_path, old_uri = entry.relative_path, entry.s3_uri
            entry.relative_path, entry.kind = path, kind
            if stored:
                entry.s3_uri, entry.checksum = stored.uri, stored.checksum
                entry.size_bytes, entry.content_type = stored.size_bytes, stored.content_type
            entry.save(update_fields=["relative_path", "kind", "s3_uri", "checksum", "size_bytes", "content_type", "updated_at"])
            if locked.entry_point == old_path:
                locked.entry_point = path if kind == "script" else ""
            _bump(locked)
            if stored and old_uri:
                transaction.on_commit(lambda: storage.delete(old_uri), robust=True)
        return entry, locked.revision
    except Exception:
        if stored:
            storage.delete(stored.uri)
        raise


def move_entry(workspace, entry_id, *, revision, path):
    safe_path(path)
    with transaction.atomic():
        locked = _lock(workspace, revision)
        entry = locked.entries.select_for_update().get(public_id=entry_id)
        old = entry.relative_path
        if entry.kind == "requirements" or path == old or path.startswith(old + "/"):
            raise ValidationError({"path": "This move is not allowed."})
        if PurePosixPath(path).name.lower() == "requirements.txt":
            raise ValidationError({"path": "requirements.txt is reserved."})
        if entry.kind != "folder" and not path.lower().endswith(EXTENSIONS[entry.kind]):
            raise ValidationError({"path": "The file extension does not match its type."})
        _parent_exists(locked, path)
        entries = list(locked.entries.select_for_update().filter(relative_path__startswith=old + "/")) if entry.kind == "folder" else []
        entries.append(entry)
        old_paths = {item.relative_path for item in entries}
        targets = {path + item.relative_path[len(old):] for item in entries}
        if locked.entries.filter(relative_path__in=targets).exclude(relative_path__in=old_paths).exists():
            raise Conflict("A file or folder already exists at this path.")
        for item in entries:
            item.relative_path = path + item.relative_path[len(old):]
            item.save(update_fields=["relative_path", "updated_at"])
        if locked.entry_point == old or locked.entry_point.startswith(old + "/"):
            locked.entry_point = path + locked.entry_point[len(old):]
        _bump(locked)
        return locked.revision


def delete_entry(workspace, entry_id, *, revision, storage=None):
    storage = storage or S3Storage()
    with transaction.atomic():
        locked = _lock(workspace, revision)
        entry = locked.entries.select_for_update().get(public_id=entry_id)
        path = entry.relative_path
        rows = locked.entries.filter(relative_path__startswith=path + "/") | locked.entries.filter(pk=entry.pk)
        uris = list(rows.exclude(s3_uri="").values_list("s3_uri", flat=True))
        rows.delete()
        if locked.entry_point == path or locked.entry_point.startswith(path + "/"):
            locked.entry_point = ""
        _bump(locked)
        for uri in uris:
            transaction.on_commit(lambda uri=uri: storage.delete(uri), robust=True)
        return locked.revision


def cipher():
    try:
        key = getattr(settings, "TRAINING_SECRET_ENCRYPTION_KEY", "")
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ServiceUnavailable("Training secrets are not configured.") from exc


def set_secret(workspace, *, revision, name, value):
    validate_name(name)
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 8192:
        raise ValidationError({"value": "Enter a secret value of at most 8192 bytes."})
    encrypted = cipher().encrypt(value.encode("utf-8"))
    with transaction.atomic():
        locked = _lock(workspace, revision)
        if name in locked.environment:
            raise Conflict("This name is already used by an environment variable.")
        if not locked.secrets.filter(name=name).exists() and locked.secrets.count() >= 100:
            raise ValidationError({"name": "At most 100 secrets are supported per workspace."})
        secret, _ = TrainingJobSecret.objects.update_or_create(job=locked, name=name,
            defaults={"ciphertext": encrypted})
        _bump(locked)
        return secret, locked.revision


def delete_secret(workspace, *, revision, name):
    with transaction.atomic():
        locked = _lock(workspace, revision, terminal_secret=True)
        count, _ = locked.secrets.filter(name=name).delete()
        if not count:
            raise ValidationError({"name": "Secret does not exist."})
        _bump(locked)
        return locked.revision
