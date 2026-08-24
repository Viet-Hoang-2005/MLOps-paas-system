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


class S3Storage:
    def __init__(self, client=None, bucket=None):
        kwargs = {"region_name": settings.AWS_S3_REGION_NAME}
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

    def presigned_get(self, uri, expires_in=900):
        bucket, key = self.parse_uri(uri)
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
        )

    def presigned_put(self, uri, expires_in=900, content_type=None):
        bucket, key = self.parse_uri(uri)
        params = {"Bucket": bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
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

    def copy(self, source_uri, destination_key):
        source_bucket, source_key = self.parse_uri(source_uri)
        self.client.copy_object(
            Bucket=self.bucket,
            Key=destination_key,
            CopySource={"Bucket": source_bucket, "Key": source_key},
        )
        response = self.client.head_object(Bucket=self.bucket, Key=destination_key)
        metadata = response.get("Metadata", {})
        return StoredObject(
            destination_key,
            f"s3://{self.bucket}/{destination_key}",
            metadata.get("sha256", ""),
            response.get("ContentLength", 0),
            response.get("ContentType", "application/octet-stream"),
        )

    @staticmethod
    def parse_uri(uri):
        if not uri.startswith("s3://"):
            raise ValueError("Expected an s3:// URI")
        bucket, key = uri[5:].split("/", 1)
        return bucket, key
