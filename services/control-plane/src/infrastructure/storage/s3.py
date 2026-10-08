import hashlib
from dataclasses import dataclass

import boto3
from django.conf import settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    uri: str
    checksum: str
    size_bytes: int
    content_type: str
    etag: str = ""


class S3Storage:
    def __init__(self, client=None, bucket=None, client_config=None):
        kwargs = {"region_name": settings.AWS_S3_REGION_NAME}
        if client_config is not None:
            kwargs["config"] = client_config
        if settings.AWS_S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.AWS_S3_ENDPOINT_URL
        self.client = client or boto3.client("s3", **kwargs)
        self.bucket = bucket or settings.AWS_STORAGE_BUCKET_NAME

    def put(self, key, body, content_type="application/octet-stream"):
        payload = body.read() if hasattr(body, "read") else body
        if isinstance(payload, str):
            payload = payload.encode()
        checksum = hashlib.sha256(payload).hexdigest()
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=payload, ContentType=content_type, Metadata={"sha256": checksum}
        )
        return StoredObject(key, f"s3://{self.bucket}/{key}", checksum, len(payload), content_type)

    def download_file(self, uri, destination):
        bucket, key = self.parse_uri(uri)
        self.client.download_file(bucket, key, str(destination))

    def read(self, uri, max_bytes=4 * 1024 * 1024):
        bucket, key = self.parse_uri(uri)
        body = self.client.get_object(Bucket=bucket, Key=key)["Body"]
        try:
            value = body.read(max_bytes + 1)
        finally:
            body.close()
        if len(value) > max_bytes:
            raise ValueError("Object exceeds the allowed read size.")
        return value

    def compute_sha256(self, uri: str) -> str:
        bucket, key = self.parse_uri(uri)
        response = self.client.get_object(Bucket=bucket, Key=key)
        hasher = hashlib.sha256()
        body = response["Body"]
        try:
            while chunk := body.read(1024 * 1024):
                hasher.update(chunk)
        finally:
            body.close()
        return hasher.hexdigest()

    def head(self, uri: str) -> StoredObject:
        bucket, key = self.parse_uri(uri)
        response = self.client.head_object(Bucket=bucket, Key=key)
        metadata = response.get("Metadata", {})
        etag = response.get("ETag", "").strip('"')
        checksum = metadata.get("sha256") or etag
        return StoredObject(
            key=key,
            uri=uri,
            checksum=checksum,
            size_bytes=response.get("ContentLength", 0),
            content_type=response.get("ContentType", "application/octet-stream"),
            etag=response.get("ETag", ""),
        )

    def presigned_get(self, uri, expires_in=900):
        bucket, key = self.parse_uri(uri)
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
        )

    def presigned_put(self, uri, expires_in=900, content_type=None, size_bytes=None):
        bucket, key = self.parse_uri(uri)
        params = {"Bucket": bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        if size_bytes is not None:
            params["ContentLength"] = size_bytes
        return self.client.generate_presigned_url("put_object", Params=params, ExpiresIn=expires_in)

    def delete_prefix(self, prefix):
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})

    def delete(self, uri):
        bucket, key = self.parse_uri(uri)
        self.client.delete_object(Bucket=bucket, Key=key)

    def copy(self, source_uri, destination_key, checksum=None, content_type=None, size_bytes=None, expected_etag=None):
        source_bucket, source_key = self.parse_uri(source_uri)
        if not checksum or not content_type or size_bytes is None:
            source_head = self.head(source_uri)
            checksum = checksum or source_head.checksum
            content_type = content_type or source_head.content_type
            size_bytes = size_bytes if size_bytes is not None else source_head.size_bytes

        options = {"CopySourceIfMatch": expected_etag} if expected_etag else {}
        self.client.copy_object(
            Bucket=self.bucket,
            Key=destination_key,
            CopySource={"Bucket": source_bucket, "Key": source_key},
            Metadata={"sha256": checksum},
            MetadataDirective="REPLACE",
            ContentType=content_type,
            **options,
        )
        return StoredObject(
            destination_key,
            f"s3://{self.bucket}/{destination_key}",
            checksum,
            size_bytes,
            content_type,
        )

    @staticmethod
    def parse_uri(uri):
        if not uri.startswith("s3://"):
            raise ValueError("Expected an s3:// URI")
        bucket, key = uri[5:].split("/", 1)
        return bucket, key
