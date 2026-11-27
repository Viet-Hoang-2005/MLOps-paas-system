import hashlib
import logging
import uuid
from dataclasses import dataclass

from botocore.exceptions import ClientError
from django.core import signing
from rest_framework.exceptions import ValidationError

from common.validation.artifacts import MAX_REFERENCE_DATA_BYTES, validate_reference_data_content
from infrastructure.storage import S3Storage

logger = logging.getLogger(__name__)
CSV_UPLOAD_TTL = 900
CSV_CONTENT_TYPE = "text/csv"
_SALT = "staged-csv-upload"


def _scope(resource, purpose, revision):
    owner = resource.project.owner if purpose in {"version", "drift-monitor"} else resource.owner
    return [owner.tenant_id, purpose, str(resource.public_id), str(revision) if revision is not None else ""]


def _key(scope, upload_id):
    tenant, purpose, resource_id, _revision = scope
    return f"staging/users/{tenant}/csv/{purpose}/{resource_id}/{upload_id}.csv"


def issue_csv_upload(resource, purpose, *, filename, size, revision=None, storage=None):
    if (
        len(filename) > 255 or not filename.lower().endswith(".csv")
        or any(char in filename for char in ("/", "\\", "\x00"))
    ):
        raise ValidationError({"filename": "Use a plain CSV filename."})
    if not 0 < size <= MAX_REFERENCE_DATA_BYTES:
        raise ValidationError({"size_bytes": "CSV must be between 1 byte and 100 MiB."})
    storage = storage or S3Storage()
    scope = _scope(resource, purpose, revision)
    upload_id = uuid.uuid4().hex
    uri = f"s3://{storage.bucket}/{_key(scope, upload_id)}"
    return {
        "upload_url": storage.presigned_put(uri, CSV_UPLOAD_TTL, CSV_CONTENT_TYPE, size, public=True),
        "content_type": CSV_CONTENT_TYPE,
        "upload_token": signing.dumps(
            {"scope": scope, "id": upload_id, "filename": filename, "size": size}, salt=_SALT
        ),
    }


@dataclass(frozen=True)
class StagedCSV:
    filename: str
    key: str
    size: int
    error_field: str

    def promote(self, storage, destination):
        uri = f"s3://{storage.bucket}/{self.key}"
        try:
            source = storage.head(uri)
            if source.size_bytes != self.size or source.content_type != CSV_CONTENT_TYPE or not source.etag:
                raise ValidationError({self.error_field: "Uploaded CSV does not match the upload request."})
            # Read and copy the same object revision even if the upload URL is reused.
            payload = storage.read(uri, max_bytes=self.size, expected_etag=source.etag)
            if len(payload) != self.size:
                raise ValidationError({self.error_field: "Uploaded CSV does not match the upload request."})
            validate_reference_data_content(self.filename, payload, error_key=self.error_field)
            stored = storage.copy(
                uri, destination, checksum=hashlib.sha256(payload).hexdigest(),
                content_type=CSV_CONTENT_TYPE, size_bytes=self.size, expected_etag=source.etag,
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound", "412", "PreconditionFailed"}:
                raise ValidationError({self.error_field: "Uploaded CSV is missing or changed. Upload it again."}) from exc
            raise
        try:
            storage.delete(uri)
        except Exception:
            logger.warning("Could not remove staged CSV after promotion.", exc_info=True)
        return stored


def resolve_csv_upload(token, resource, purpose, *, revision=None, error_field):
    if not isinstance(token, str) or not token:
        raise ValidationError({error_field: "An upload token is required."})
    try:
        claims = signing.loads(token, salt=_SALT, max_age=CSV_UPLOAD_TTL)
    except signing.BadSignature as exc:
        raise ValidationError({error_field: "Invalid or expired CSV upload. Upload the file again."}) from exc
    scope = _scope(resource, purpose, revision)
    if claims["scope"] != scope:
        raise ValidationError({error_field: "This CSV upload belongs to a different resource or revision."})
    return StagedCSV(claims["filename"], _key(scope, claims["id"]), claims["size"], error_field)
