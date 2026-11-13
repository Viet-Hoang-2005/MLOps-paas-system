from urllib.parse import parse_qs, urlparse

import pytest
from botocore.config import Config

from infrastructure.storage import S3Storage


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret-key")


def _query(url):
    return parse_qs(urlparse(url).query)


def test_presigned_put_signs_content_length_and_type():
    url = S3Storage(bucket="bucket").presigned_put(
        "s3://bucket/staging/model.pkl", content_type="application/octet-stream", size_bytes=1234
    )
    query = _query(url)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    signed_headers = set(query["X-Amz-SignedHeaders"][0].split(";"))
    assert {"content-length", "content-type", "host"} <= signed_headers


def test_custom_client_config_keeps_sigv4():
    storage = S3Storage(bucket="bucket", client_config=Config(connect_timeout=3, retries={"max_attempts": 0}))
    assert storage.client.meta.config.signature_version == "s3v4"
    assert storage.client.meta.config.connect_timeout == 3
    assert "X-Amz-Signature" in _query(storage.presigned_get("s3://bucket/key"))
