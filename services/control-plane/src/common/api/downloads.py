from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage


def scoped_download_response(uri, *, prefix, filename, storage=None):
    if not uri:
        raise NotFound("File is unavailable.")
    storage = storage or S3Storage()
    try:
        bucket, key = storage.parse_uri(uri)
    except ValueError as exc:
        raise Conflict("File has an invalid storage scope.") from exc
    if bucket != storage.bucket or not key.startswith(prefix):
        raise Conflict("File has an invalid storage scope.")
    url = storage.presigned_get(uri, expires_in=300, public=True, filename=filename)
    return Response({"download_url": url}, headers={"Cache-Control": "private, no-store"})
