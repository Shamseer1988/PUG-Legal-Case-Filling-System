"""Cloudflare R2 (S3-compatible) off-site backup destination.

Powers the "Weekly cloud backup" tick and the "Backup now + cloud"
button. Credentials live in the ``backup.offsite_s3_*`` settings keys
so an admin can rotate them without touching env vars.

Note: boto3 is an optional dependency. We import it lazily so the rest
of the app keeps booting even when boto3 isn't installed (e.g. during
local SQLite-only test runs).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy.orm import Session

from app.services import settings_service


class CloudUnavailable(RuntimeError):
    """boto3 missing, settings incomplete, or the provider rejected the
    request. The caller's job is to surface this to the operator -
    silently skipping a cloud push hides data loss."""


def _split_bucket_prefix(s3_url: str) -> tuple[str, str]:
    """``s3://bucket/folder/sub`` -> ``("bucket", "folder/sub")``."""
    if not s3_url:
        return "", ""
    p = urlparse(s3_url)
    bucket = p.netloc
    prefix = p.path.lstrip("/").rstrip("/")
    return bucket, prefix


def _client_from_settings(db: Session) -> tuple[Any, str, str, str]:
    """Build a boto3 S3 client targeting the configured R2 endpoint.

    Returns (client, bucket, prefix, endpoint). Raises ``CloudUnavailable``
    on any missing piece.
    """
    try:
        import boto3  # type: ignore[import-not-found]
        from botocore.config import Config  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise CloudUnavailable(
            "boto3 is not installed. Add 'boto3' to requirements.txt "
            "and restart the backend to enable off-site cloud backups."
        ) from e

    s3_url = settings_service.get_str(db, "backup.offsite_s3_url", "")
    access_key = settings_service.get_str(db, "backup.offsite_s3_access_key", "")
    secret_key = settings_service.get_str(db, "backup.offsite_s3_secret_key", "")
    endpoint = settings_service.get_str(db, "integrations.s3_endpoint", "")
    if not all([s3_url, access_key, secret_key, endpoint]):
        raise CloudUnavailable(
            "Cloud destination not configured. Set Cloud provider + folder "
            "on the Backup settings card and S3 access/secret/endpoint in "
            "Integrations."
        )

    bucket, prefix = _split_bucket_prefix(s3_url)
    if not bucket:
        raise CloudUnavailable(
            f"Cloud / external folder is invalid: '{s3_url}'. "
            f"Expected an S3 URL like s3://my-bucket/legal-backups."
        )

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        # R2 uses path-style addressing.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    return client, bucket, prefix, endpoint


def is_configured(db: Session) -> bool:
    """Cheap check - does NOT touch the network."""
    return all(
        settings_service.get_str(db, k, "")
        for k in (
            "backup.offsite_s3_url",
            "backup.offsite_s3_access_key",
            "backup.offsite_s3_secret_key",
            "integrations.s3_endpoint",
        )
    )


def test_connection(db: Session) -> dict[str, Any]:
    """Light HEAD on the bucket to validate credentials + endpoint
    reachability. Returns ``{ok, message, bucket, prefix, endpoint}``.
    Never raises - the UI just renders the result.
    """
    try:
        client, bucket, prefix, endpoint = _client_from_settings(db)
        client.head_bucket(Bucket=bucket)
        return {
            "ok": True,
            "message": "Connection OK",
            "bucket": bucket,
            "prefix": prefix,
            "endpoint": endpoint,
        }
    except CloudUnavailable as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:  # boto3 ClientError or network
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}


def upload_file(db: Session, local_path: Path, *, key_suffix: str = "") -> str:
    """Upload ``local_path`` to ``s3://bucket/prefix/[suffix]filename``.
    Returns the full key (relative to bucket). Raises CloudUnavailable
    on any failure so the caller can record it.
    """
    client, bucket, prefix, _ = _client_from_settings(db)
    name = local_path.name
    key_parts = [p for p in (prefix, key_suffix, name) if p]
    key = "/".join(key_parts)
    try:
        client.upload_file(str(local_path), bucket, key)
    except Exception as e:
        raise CloudUnavailable(f"R2 upload failed: {e}") from e
    logger.info("Uploaded {} -> r2://{}/{}", local_path.name, bucket, key)
    return key


def list_objects(db: Session) -> list[dict[str, Any]]:
    """Return objects under the configured prefix:
    ``[{key, name, size, last_modified}, ...]``. Filters to only ``.dump``
    files so the UI never offers to restore a stray ``.txt`` README an
    admin dropped in the bucket.
    """
    try:
        client, bucket, prefix, _ = _client_from_settings(db)
    except CloudUnavailable as e:
        logger.warning("R2 list skipped: {}", e)
        return []
    p_prefix = prefix + "/" if prefix and not prefix.endswith("/") else prefix
    paginator = client.get_paginator("list_objects_v2")
    out: list[dict[str, Any]] = []
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=p_prefix):
            for obj in page.get("Contents", []) or []:
                key = obj["Key"]
                if not key.endswith(".dump"):
                    continue
                out.append(
                    {
                        "key": key,
                        "name": key.rsplit("/", 1)[-1],
                        "size": obj.get("Size", 0),
                        "last_modified": obj.get("LastModified").isoformat()
                        if obj.get("LastModified")
                        else None,
                    }
                )
    except Exception as e:
        logger.warning("R2 list failed: {}", e)
        return []
    # Newest first - operators expect the latest at the top.
    out.sort(key=lambda r: r["last_modified"] or "", reverse=True)
    return out


def download_object(db: Session, key: str, dest: Path) -> None:
    client, bucket, _, _ = _client_from_settings(db)
    try:
        client.download_file(bucket, key, str(dest))
    except Exception as e:
        raise CloudUnavailable(f"R2 download failed: {e}") from e
