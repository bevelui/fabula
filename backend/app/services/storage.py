# -*- coding: utf-8 -*-
"""Cloudflare R2 storage (S3-compatible). Durable, off-server storage for finished
files, served via short-lived presigned URLs so the bucket stays private.

Inert unless all R2_* env vars are set — the app falls back to the local volume.
boto3 is imported lazily so the app runs fine without R2 configured.
"""
import os
from ..config import settings


def enabled():
    return all([settings.R2_ACCOUNT_ID, settings.R2_ACCESS_KEY_ID,
                settings.R2_SECRET_ACCESS_KEY, settings.R2_BUCKET])


def _client():
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def upload_dir(pid, local_dir, log=lambda m: None):
    """Upload everything under a project's output folder to R2 as <pid>/<relpath>."""
    if not enabled() or not os.path.isdir(local_dir):
        return 0
    c = _client()
    n = 0
    for root, _dirs, files in os.walk(local_dir):
        for fn in files:
            full = os.path.join(root, fn)
            key = f"{pid}/" + os.path.relpath(full, local_dir).replace(os.sep, "/")
            c.upload_file(full, settings.R2_BUCKET, key)
            n += 1
    log(f"uploaded {n} files to R2 (durable storage)")
    return n


def presigned_url(pid, name, expires=3600):
    """A temporary download URL for a private R2 object."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": f"{pid}/{name}"},
        ExpiresIn=expires,
    )
