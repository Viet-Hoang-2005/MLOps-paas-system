"""Bootstrap the default S3 bucket when running against local MinIO."""

import os
import time
import urllib.request

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def resolve_minio_config() -> tuple[str, str, str] | None:
    endpoint = os.environ.get("AWS_S3_ENDPOINT_URL", "").strip()
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    has_real_aws_keys = bool(access_key and secret_key and access_key != "minioadmin")

    if not endpoint:
        if has_real_aws_keys:
            return None
        endpoint = "http://minio:9000"

    if not access_key:
        os.environ["AWS_ACCESS_KEY_ID"] = os.environ.get("MINIO_ROOT_USER", "").strip() or "minioadmin"
    if not secret_key:
        os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ.get("MINIO_ROOT_PASSWORD", "").strip() or "minioadmin"

    bucket = os.environ.get("AWS_BUCKET_NAME", "mlops-paas-artifacts").strip() or "mlops-paas-artifacts"
    region = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1").strip() or "ap-southeast-1"
    return endpoint, bucket, region


def wait_for_minio(endpoint: str, *, attempts: int = 30, delay_seconds: float = 2.0) -> None:
    health_url = endpoint.rstrip("/") + "/minio/health/live"
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(delay_seconds)
    raise SystemExit(f"MinIO did not become ready at {health_url}")


def ensure_bucket(endpoint: str, bucket: str, region: str) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchBucket", "NotFound"}:
            client.create_bucket(Bucket=bucket)
        else:
            raise
    client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
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


def main() -> int:
    resolved = resolve_minio_config()
    if resolved is None:
        return 0
    endpoint, bucket, region = resolved
    wait_for_minio(endpoint)
    ensure_bucket(endpoint, bucket, region)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
