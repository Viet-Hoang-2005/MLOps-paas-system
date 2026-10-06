import hashlib
import io
from unittest.mock import MagicMock

from infrastructure.storage.s3 import S3Storage


def test_s3storage_head_uses_metadata_sha256_when_present():
    client = MagicMock()
    client.head_object.return_value = {
        "Metadata": {"sha256": "precalculated-sha256-hex-digest"},
        "ETag": '"md5-etag-value"',
        "ContentLength": 1024,
        "ContentType": "application/octet-stream",
    }

    storage = S3Storage(client=client, bucket="test-bucket")
    stored = storage.head("s3://test-bucket/models/model.pkl")

    assert stored.checksum == "precalculated-sha256-hex-digest"
    assert stored.checksum != "md5-etag-value"
    client.head_object.assert_called_once_with(Bucket="test-bucket", Key="models/model.pkl")
    client.get_object.assert_not_called()


def test_s3storage_head_computes_sha256_when_metadata_missing_ignoring_etag():
    content = b"presigned-uploaded-model-weights-bytes"
    expected_sha256 = hashlib.sha256(content).hexdigest()

    client = MagicMock()
    # Presigned upload direct to S3 leaves Metadata empty, only ETag is provided by S3
    client.head_object.return_value = {
        "Metadata": {},
        "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',
        "ContentLength": len(content),
        "ContentType": "application/octet-stream",
    }
    client.get_object.return_value = {
        "Body": io.BytesIO(content),
    }

    storage = S3Storage(client=client, bucket="test-bucket")
    stored = storage.head("s3://test-bucket/staging/users/u1/models/m1/preview/model.pkl")

    # Checksum MUST be the real SHA-256 (64 hex characters), NEVER the MD5 ETag
    assert stored.checksum == expected_sha256
    assert stored.checksum != "d41d8cd98f00b204e9800998ecf8427e"
    assert len(stored.checksum) == 64
    client.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="staging/users/u1/models/m1/preview/model.pkl"
    )


def test_s3storage_copy_attaches_sha256_metadata_and_preserves_content_type():
    client = MagicMock()
    source_content = b"model-artifact-to-promote"
    expected_sha256 = hashlib.sha256(source_content).hexdigest()

    # Source has no sha256 in metadata
    client.head_object.return_value = {
        "Metadata": {},
        "ETag": '"some-md5-etag"',
        "ContentLength": len(source_content),
        "ContentType": "application/x-pickle",
    }
    client.get_object.return_value = {
        "Body": io.BytesIO(source_content),
    }

    storage = S3Storage(client=client, bucket="test-bucket")
    destination_key = "users/u1/models/m1/preview/committed/token/source_artifact/model.pkl"
    stored = storage.copy("s3://test-bucket/staging/model.pkl", destination_key)

    assert stored.checksum == expected_sha256
    assert stored.size_bytes == len(source_content)
    assert stored.content_type == "application/x-pickle"

    # Verify copy_object sets MetadataDirective='REPLACE' and writes sha256 to S3 metadata
    client.copy_object.assert_called_once_with(
        Bucket="test-bucket",
        Key=destination_key,
        CopySource={"Bucket": "test-bucket", "Key": "staging/model.pkl"},
        Metadata={"sha256": expected_sha256},
        MetadataDirective="REPLACE",
        ContentType="application/x-pickle",
    )


def test_s3storage_copy_with_explicit_checksum_bypasses_extra_head():
    client = MagicMock()
    storage = S3Storage(client=client, bucket="test-bucket")
    destination_key = "users/u1/models/m1/committed/model.pkl"

    stored = storage.copy(
        "s3://test-bucket/staging/model.pkl",
        destination_key,
        checksum="known-sha256",
        content_type="application/octet-stream",
        size_bytes=512,
    )

    assert stored.checksum == "known-sha256"
    assert stored.size_bytes == 512
    assert stored.content_type == "application/octet-stream"

    # Since all attributes were provided, head_object/get_object were not called
    client.head_object.assert_not_called()
    client.get_object.assert_not_called()
    client.copy_object.assert_called_once_with(
        Bucket="test-bucket",
        Key=destination_key,
        CopySource={"Bucket": "test-bucket", "Key": "staging/model.pkl"},
        Metadata={"sha256": "known-sha256"},
        MetadataDirective="REPLACE",
        ContentType="application/octet-stream",
    )

