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


def test_minio_dual_endpoint_presigned_urls(settings):
    settings.AWS_S3_ENDPOINT_URL = "http://minio:9000"
    settings.AWS_S3_PUBLIC_ENDPOINT_URL = "http://localhost:9000"
    storage = S3Storage(bucket="mlops-paas-artifacts")

    internal_get = urlparse(storage.presigned_get("s3://mlops-paas-artifacts/path/file.csv"))
    public_get = urlparse(storage.presigned_get("s3://mlops-paas-artifacts/path/file.csv", public=True))
    public_put = urlparse(
        storage.presigned_put(
            "s3://mlops-paas-artifacts/path/model.pkl",
            content_type="application/octet-stream",
            size_bytes=512,
            public=True,
        )
    )

    assert internal_get.netloc == "minio:9000"
    assert internal_get.path == "/mlops-paas-artifacts/path/file.csv"
    assert public_get.netloc == "localhost:9000"
    assert public_get.path == "/mlops-paas-artifacts/path/file.csv"
    assert "X-Amz-Signature" in parse_qs(public_get.query)
    assert public_put.netloc == "localhost:9000"
    assert public_put.path == "/mlops-paas-artifacts/path/model.pkl"
    assert "X-Amz-Signature" in parse_qs(public_put.query)


def test_django_storage_uses_public_endpoint_for_url(settings):
    from infrastructure.storage.django_storage import PublicPresignedS3Storage

    settings.AWS_S3_ENDPOINT_URL = "http://minio:9000"
    settings.AWS_S3_PUBLIC_ENDPOINT_URL = "http://localhost:9000"
    settings.AWS_STORAGE_BUCKET_NAME = "mlops-paas-artifacts"
    storage = PublicPresignedS3Storage()

    parsed = urlparse(storage.url("users/tenant/avatar/pic.png"))
    assert parsed.netloc == "localhost:9000"
    assert parsed.path == "/mlops-paas-artifacts/users/tenant/avatar/pic.png"
    assert "X-Amz-Signature" in parse_qs(parsed.query)


def test_init_minio_skips_when_real_aws_keys_set(monkeypatch):
    from infrastructure.storage import init_minio

    monkeypatch.delenv("AWS_S3_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
    assert init_minio.resolve_minio_config() is None
    assert init_minio.main() == 0


def test_init_minio_defaults_to_minio_when_aws_keys_empty(monkeypatch):
    import os
    from infrastructure.storage import init_minio

    monkeypatch.delenv("AWS_S3_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    monkeypatch.setenv("MINIO_ROOT_USER", "custom-minio-user")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "custom-minio-pass")
    assert init_minio.resolve_minio_config() == ("http://minio:9000", "mlops-paas-artifacts", "ap-southeast-1")
    assert os.environ["AWS_ACCESS_KEY_ID"] == "custom-minio-user"
    assert os.environ["AWS_SECRET_ACCESS_KEY"] == "custom-minio-pass"


def test_drop_empty_put_expect_removes_expect_for_zero_length():
    from types import SimpleNamespace
    from infrastructure.storage.s3 import _drop_empty_put_expect

    empty_req = SimpleNamespace(headers={"Content-Length": "0", "Expect": "100-continue"})
    _drop_empty_put_expect(empty_req)
    assert "Expect" not in empty_req.headers

    non_empty_req = SimpleNamespace(headers={"Content-Length": "42", "Expect": "100-continue"})
    _drop_empty_put_expect(non_empty_req)
    assert non_empty_req.headers["Expect"] == "100-continue"


def test_init_minio_creates_missing_bucket(monkeypatch):
    from unittest.mock import Mock
    from botocore.exceptions import ClientError
    from infrastructure.storage import init_minio

    client = Mock()
    client.head_bucket.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadBucket")
    monkeypatch.setattr(init_minio.boto3, "client", lambda *args, **kwargs: client)

    init_minio.ensure_bucket("http://minio:9000", "mlops-paas-artifacts", "ap-southeast-1")
    client.head_bucket.assert_called_once_with(Bucket="mlops-paas-artifacts")
    client.create_bucket.assert_called_once_with(Bucket="mlops-paas-artifacts")
    client.put_bucket_lifecycle_configuration.assert_called_once_with(
        Bucket="mlops-paas-artifacts",
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "ephemeral-staging-cleanup",
                    "Filter": {"Prefix": "staging/"},
                    "Status": "Enabled",
                    "Expiration": {"Days": 1},
                }
            ]
        },
    )
