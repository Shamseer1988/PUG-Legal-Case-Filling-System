"""Local filesystem storage for case attachments.

Phase 36: files for a case live under
``STORAGE_LOCAL_PATH/cases/<case_no>/`` once the case has a case
number minted, otherwise under ``cases/case-<id>/``. Cheque-level
files live under ``.../cheques/cheque-<cheque_id>/``. Transition
files live under ``.../transitions/``.

Old layouts (``cases/<case_id>/...``) keep being readable: the
lookup helpers fall back to that path so existing rows can still
download their file, and ``ensure_case_dir`` migrates the folder
to the new ``case_no`` name on the next write.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.models.case import Case

CASES_SUBDIR = "cases"
SIGNATURES_SUBDIR = "signatures"
TRANSITIONS_SUBDIR = "transitions"
CHEQUES_SUBDIR = "cheques"
PARTNERS_SUBDIR = "partners"

# Image MIME -> file extension for signature uploads
_SIG_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# Only [A-Za-z0-9_-] make it into a folder name. Anything else is
# replaced with ``_`` so we never write outside the storage root
# even if a malicious case_no somehow lands in the DB.
_SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_folder(value: str) -> str:
    cleaned = _SAFE_PATH_RE.sub("_", value).strip("._-")
    return cleaned or "untitled"


def _cases_root() -> Path:
    p = settings.storage_path / CASES_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def case_folder_name(case: Case) -> str:
    """Human-readable folder name for a Case.

    Uses ``case_no`` when assigned, falls back to ``case-<id>`` for
    drafts that haven't been written yet (rare - case_no is minted
    on first save).
    """
    if case.case_no:
        return _safe_folder(case.case_no)
    return f"case-{case.id}"


def _legacy_case_dir(case_id: int) -> Path:
    return _cases_root() / str(case_id)


def ensure_case_dir(case: Case) -> Path:
    """Return the on-disk directory for the case, migrating from a
    pre-Phase 36 legacy ``<case_id>`` folder if one exists. Safe to
    call repeatedly - migration only runs when both folders aren't
    already the same.
    """
    target = _cases_root() / case_folder_name(case)
    legacy = _legacy_case_dir(case.id)
    if legacy.exists() and legacy != target and not target.exists():
        # Old layout still on disk - move it.
        try:
            legacy.rename(target)
        except OSError:
            # Cross-device or permission issue - copy then drop.
            target.mkdir(parents=True, exist_ok=True)
            for f in legacy.iterdir():
                shutil.move(str(f), str(target / f.name))
            try:
                legacy.rmdir()
            except OSError:
                pass
    target.mkdir(parents=True, exist_ok=True)
    return target


def _resolve_existing_case_dir(case: Case) -> Path:
    """Where to READ from. Prefers the new ``case_no`` directory
    but falls back to the legacy ``<case_id>`` one for files that
    never got migrated."""
    target = _cases_root() / case_folder_name(case)
    if target.exists():
        return target
    legacy = _legacy_case_dir(case.id)
    if legacy.exists():
        return legacy
    return target  # caller will mkdir/handle missing-file errors


def _signatures_dir() -> Path:
    p = settings.storage_path / SIGNATURES_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


# ===================== Signatures =====================
def save_user_signature(user_id: int, upload: UploadFile) -> tuple[str, int]:
    """Save a user signature image to storage/signatures/<user_id>.<ext>.

    Replaces any pre-existing signature for that user so we don't
    accumulate orphaned files. Returns (relative_path, size_bytes).
    """
    mime = (upload.content_type or "").lower()
    ext = _SIG_MIME_EXT.get(mime)
    if not ext:
        guess = Path(upload.filename or "").suffix.lower()
        if guess in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            ext = ".jpg" if guess == ".jpeg" else guess
    if not ext:
        raise ValueError("Unsupported signature image format")

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
    return settings.storage_path / relative_path


def delete_user_signature(relative_path: str) -> None:
    p = get_user_signature_path(relative_path)
    if p.exists():
        p.unlink()


# ===================== Case attachments =====================
def save_case_attachment(case: Case, upload: UploadFile) -> tuple[str, int]:
    """Stream-save the upload. Returns (stored_filename, size_bytes)."""
    original = upload.filename or "file"
    ext = Path(original).suffix
    stored = f"{uuid.uuid4().hex}{ext}"
    target_dir = ensure_case_dir(case)
    target = target_dir / stored

    size = 0
    with target.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)

    return stored, size


def get_case_attachment_path(case: Case, stored_filename: str) -> Path:
    """Look up an attachment, falling back to the legacy
    ``<case_id>`` folder so files uploaded pre-Phase-36 still work
    even before ``ensure_case_dir`` runs."""
    primary = _resolve_existing_case_dir(case) / stored_filename
    if primary.exists():
        return primary
    legacy = _legacy_case_dir(case.id) / stored_filename
    if legacy.exists():
        return legacy
    return primary  # caller decides how to handle missing


def delete_case_attachment(case: Case, stored_filename: str) -> None:
    p = get_case_attachment_path(case, stored_filename)
    if p.exists():
        p.unlink()


def delete_case_dir(case: Case) -> None:
    for d in (
        _cases_root() / case_folder_name(case),
        _legacy_case_dir(case.id),
    ):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


# ===================== Cheque attachments (Phase 36) =====================
def _cheque_dir(case: Case, cheque_id: int) -> Path:
    p = ensure_case_dir(case) / CHEQUES_SUBDIR / f"cheque-{cheque_id}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_cheque_attachment(
    case: Case, cheque_id: int, upload: UploadFile
) -> tuple[str, int]:
    original = upload.filename or "file"
    ext = Path(original).suffix
    stored = f"{uuid.uuid4().hex}{ext}"
    target = _cheque_dir(case, cheque_id) / stored
    size = 0
    with target.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    return stored, size


def get_cheque_attachment_path(
    case: Case, cheque_id: int, stored_filename: str
) -> Path:
    return _cheque_dir(case, cheque_id) / stored_filename


def delete_cheque_attachment(
    case: Case, cheque_id: int, stored_filename: str
) -> None:
    p = get_cheque_attachment_path(case, cheque_id, stored_filename)
    if p.exists():
        p.unlink()


# ===================== Transition attachments =====================
def _transition_dir(case: Case) -> Path:
    p = ensure_case_dir(case) / TRANSITIONS_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_transition_attachment(case: Case, upload: UploadFile) -> tuple[str, int]:
    original = upload.filename or "file"
    ext = Path(original).suffix
    stored = f"{uuid.uuid4().hex}{ext}"
    target = _transition_dir(case) / stored
    size = 0
    with target.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    return stored, size


def get_transition_attachment_path(case: Case, stored_filename: str) -> Path:
    primary = _transition_dir(case) / stored_filename
    if primary.exists():
        return primary
    legacy = _legacy_case_dir(case.id) / TRANSITIONS_SUBDIR / stored_filename
    if legacy.exists():
        return legacy
    return primary


def delete_transition_attachment(case: Case, stored_filename: str) -> None:
    p = get_transition_attachment_path(case, stored_filename)
    if p.exists():
        p.unlink()


# ===================== Customer-partner ID documents (Phase 40) =====================
def _partner_dir(partner_id: int) -> Path:
    p = settings.storage_path / PARTNERS_SUBDIR / str(partner_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_partner_id_document(
    partner_id: int, upload: UploadFile
) -> tuple[str, int]:
    """Replace any prior ID copy with the new upload.

    Returns ``(stored_filename, size_bytes)``. The model row stores
    ``stored_filename`` as a plain name (no path) and looks the
    file back up via ``get_partner_id_document_path``.
    """
    original = upload.filename or "id"
    ext = Path(original).suffix
    # Wipe any previous ID copy for this partner so we don't
    # accumulate orphans when the operator re-uploads.
    for old in _partner_dir(partner_id).iterdir():
        try:
            old.unlink()
        except OSError:
            pass
    stored = f"{uuid.uuid4().hex}{ext}"
    target = _partner_dir(partner_id) / stored
    size = 0
    with target.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    return stored, size


def get_partner_id_document_path(partner_id: int, stored_filename: str) -> Path:
    return _partner_dir(partner_id) / stored_filename


def delete_partner_id_document(partner_id: int, stored_filename: str) -> None:
    p = get_partner_id_document_path(partner_id, stored_filename)
    if p.exists():
        p.unlink()
