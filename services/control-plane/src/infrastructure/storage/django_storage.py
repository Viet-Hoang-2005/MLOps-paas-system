import boto3
from botocore.config import Config
from django.conf import settings
from storages.backends.s3 import S3Storage as DjangoS3Storage


class PublicPresignedS3Storage(DjangoS3Storage):
    """Uses internal AWS_S3_ENDPOINT_URL for I/O and AWS_S3_PUBLIC_ENDPOINT_URL for browser URLs."""

    def url(self, name, parameters=None, expire=None, http_method=None):
        public_endpoint = getattr(settings, "AWS_S3_PUBLIC_ENDPOINT_URL", None)
        internal_endpoint = getattr(settings, "AWS_S3_ENDPOINT_URL", None)
        if not public_endpoint or public_endpoint == internal_endpoint:
            return super().url(name, parameters=parameters, expire=expire, http_method=http_method)

        params = dict(parameters or {})
        params["Bucket"] = self.bucket_name
        params["Key"] = self._normalize_name(name)
        client = boto3.client(
            "s3",
            endpoint_url=public_endpoint,
            region_name=self.region_name,
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None) or None,
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None) or None,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expire or self.querystring_expire,
            HttpMethod=http_method,
        )
