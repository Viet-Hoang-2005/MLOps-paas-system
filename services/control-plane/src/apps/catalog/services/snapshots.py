from io import BytesIO
from zipfile import ZipFile, BadZipFile
from rest_framework.exceptions import ValidationError
from infrastructure.storage import S3Storage


def running_source(project, storage=None):
    """Read only the immutable Running script; never execute or extract the archive."""
    if not project.active_deployment_id:
        return ""
    asset = project.active_deployment.version.artifacts.filter(kind="source_code").first()
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
