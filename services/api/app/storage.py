import boto3
from botocore.config import Config
from resonant_common.config import settings


def _client(endpoint: str):
    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key, region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}))


_internal, _public = _client(settings.s3_endpoint), _client(settings.s3_public_endpoint)


def put_file(path: str, key: str, content_type: str):
    _internal.upload_file(path, settings.s3_bucket, key, ExtraArgs={"ContentType": content_type})


def delete(key: str):
    _internal.delete_object(Bucket=settings.s3_bucket, Key=key)


def signed_url(key: str) -> str:
    """Short-lived GET URL; the object store serves HTTP Range requests, so seeking works."""
    return _public.generate_presigned_url("get_object", Params={"Bucket": settings.s3_bucket, "Key": key},
                                          ExpiresIn=settings.signed_url_ttl_s)
