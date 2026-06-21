"""Local filesystem storage for case attachments.

Files are written under STORAGE_LOCAL_PATH/cases/<case_id>/<uuid><ext>.
S3 will be added as an alternate backend in Phase 10.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings

CASES_SUBDIR = "cases"
SIGNATURES_SUBDIR = "signatures"

# Image MIME -> file extension for signature uploads
_SIG_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _case_dir(case_id: int) -> Path:
    p = settings.storage_path / CASES_SUBDIR / str(case_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _signatures_dir() -> Path:
    p = settings.storage_path / SIGNATURES_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_user_signature(user_id: int, upload: UploadFile) -> tuple[str, int]:
    """Save a user signature image to storage/signatures/<user_id>.<ext>.

    Replaces any pre-existing signature for that user so we don't
    accumulate orphaned files. Returns (relative_path, size_bytes).
    """
    mime = (upload.content_type or "").lower()
    ext = _SIG_MIME_EXT.get(mime)
    if not ext:
        # Fall back to the upload's extension if it's one we recognise.
        guess = Path(upload.filename or "").suffix.lower()
        if guess in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            ext = ".jpg" if guess == ".jpeg" else guess
    if not ext:
        raise ValueError("Unsupported signature image format")

    # Remove any prior signature for this user (could be a different ext).
    for old in _signatures_dir().glob(f"{user_id}.*"):
        try:
            old.unlink()
        except OSError:
            pass

    stored = f"{user_id}{ext}"
    target = _signatures_dir() / stored
    size = 0
    with target.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    return f"{SIGNATURES_SUBDIR}/{stored}", size


def get_user_signature_path(relative_path: str) -> Path:
    """Resolve a signature path stored on the User row."""
    return settings.storage_path / relative_path


def delete_user_signature(relative_path: str) -> None:
    p = get_user_signature_path(relative_path)
    if p.exists():
        p.unlink()


def save_case_attachment(case_id: int, upload: UploadFile) -> tuple[str, int]:
    """Stream-save the upload. Returns (stored_filename, size_bytes)."""
    original = upload.filename or "file"
    ext = Path(original).suffix
    stored = f"{uuid.uuid4().hex}{ext}"
    target = _case_dir(case_id) / stored

    size = 0
    with target.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)

    return stored, size


def get_case_attachment_path(case_id: int, stored_filename: str) -> Path:
    return _case_dir(case_id) / stored_filename


def delete_case_attachment(case_id: int, stored_filename: str) -> None:
    p = get_case_attachment_path(case_id, stored_filename)
    if p.exists():
        p.unlink()


def delete_case_dir(case_id: int) -> None:
    d = settings.storage_path / CASES_SUBDIR / str(case_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


# ---- Transition attachments (Phase 19) ----
TRANSITIONS_SUBDIR = "transitions"


def _transition_dir(case_id: int) -> Path:
    p = settings.storage_path / CASES_SUBDIR / str(case_id) / TRANSITIONS_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_transition_attachment(case_id: int, upload: UploadFile) -> tuple[str, int]:
    """Stream-save an approval-comment file. Returns (stored_filename, size_bytes)."""
    original = upload.filename or "file"
    ext = Path(original).suffix
    stored = f"{uuid.uuid4().hex}{ext}"
    target = _transition_dir(case_id) / stored

    size = 0
    with target.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    return stored, size


def get_transition_attachment_path(case_id: int, stored_filename: str) -> Path:
    return _transition_dir(case_id) / stored_filename


def delete_transition_attachment(case_id: int, stored_filename: str) -> None:
    p = get_transition_attachment_path(case_id, stored_filename)
    if p.exists():
        p.unlink()
