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


def _case_dir(case_id: int) -> Path:
    p = settings.storage_path / CASES_SUBDIR / str(case_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


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
