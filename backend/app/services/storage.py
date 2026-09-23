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


def upload_one(pid, local_path, name, log=lambda m: None):
    """Upload a single file to R2 as <pid>/<name> (used when one image is regenerated)."""
    if not enabled() or not os.path.isfile(local_path):
        return False
    _client().upload_file(local_path, settings.R2_BUCKET, f"{pid}/{name}")
    log(f"synced {name} to R2")
    return True


def exists(pid, name):
    """True if <pid>/<name> is in R2 (used so resume still skips finished stages after
    the local cache has been pruned)."""
    if not enabled():
        return False
    try:
        _client().head_object(Bucket=settings.R2_BUCKET, Key=f"{pid}/{name}")
        return True
    except Exception:
        return False


def count_prefix(pid, prefix):
    """How many objects are under <pid>/<prefix> in R2 (e.g. images/)."""
    if not enabled():
        return 0
    c = _client()
    n, token = 0, None
    while True:
        kw = {"Bucket": settings.R2_BUCKET, "Prefix": f"{pid}/{prefix}"}
        if token:
            kw["ContinuationToken"] = token
        resp = c.list_objects_v2(**kw)
        n += len(resp.get("Contents", []))
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return n


def download_one(pid, name, dest, log=lambda m: None):
    """Fetch <pid>/<name> from R2 to a local path (used by the render worker)."""
    if not enabled():
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    _client().download_file(settings.R2_BUCKET, f"{pid}/{name}", dest)
    log(f"pulled {name} from R2")
    return True


def download_prefix(pid, prefix, dest_dir, log=lambda m: None):
    """Fetch every object under <pid>/<prefix> into dest_dir (e.g. the images folder)."""
    if not enabled():
        return 0
    c = _client()
    n = 0
    token = None
    while True:
        kw = {"Bucket": settings.R2_BUCKET, "Prefix": f"{pid}/{prefix}"}
        if token:
            kw["ContinuationToken"] = token
        resp = c.list_objects_v2(**kw)
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            rel = key[len(f"{pid}/"):]
            dest = os.path.join(dest_dir, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            c.download_file(settings.R2_BUCKET, key, dest)
            n += 1
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    log(f"pulled {n} files under {prefix} from R2")
    return n


def presigned_url(pid, name, expires=3600):
    """A temporary download URL for a private R2 object."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": f"{pid}/{name}"},
        ExpiresIn=expires,
    )
