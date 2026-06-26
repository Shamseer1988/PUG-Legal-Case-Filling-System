"""Upload sanity-check helpers.

Reject files whose **filename extension OR sniffed magic bytes** fall
outside an allowlist. The client-supplied ``Content-Type`` header is
NOT trusted by itself — browsers (and curl) will happily report
anything for any byte stream — so we read the first few bytes off the
upload's spooled tempfile and check the real signature. After the
check the stream is rewound, so the existing ``_stream_to_disk``
helper can read from the beginning.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, UploadFile, status

# Categories the UI offers (case attachments, transition attachments,
# signed forms, custody acknowledgments). Each maps to an allowlist of
# safe (extension, magic-byte prefix) pairs.
#
# Magic numbers source: file(1)'s magic database — only entries we
# explicitly want to allow are listed.
_PDF = (b"%PDF-",)
_PNG = (b"\x89PNG\r\n\x1a\n",)
_JPEG = (b"\xff\xd8\xff",)
_GIF = (b"GIF87a", b"GIF89a")
_WEBP = (b"RIFF",)  # WebP magic is "RIFF????WEBP"; we verify "WEBP" separately
_ZIP_OR_OFFICE = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")  # zip/docx/xlsx
_OLE_OFFICE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)  # legacy .doc/.xls

# (allowed_extension, allowed_magic_prefixes)
_DOC_LIKE: tuple[tuple[str, tuple[bytes, ...]], ...] = (
    (".pdf", _PDF),
    (".png", _PNG),
    (".jpg", _JPEG),
    (".jpeg", _JPEG),
    (".gif", _GIF),
    (".webp", _WEBP),
    (".doc", _OLE_OFFICE),
    (".xls", _OLE_OFFICE),
    (".docx", _ZIP_OR_OFFICE),
    (".xlsx", _ZIP_OR_OFFICE),
    (".ppt", _OLE_OFFICE),
    (".pptx", _ZIP_OR_OFFICE),
)

# Stricter set for signed-form uploads (PDF + images only — never an
# editable document).
_SIGNED_FORM: tuple[tuple[str, tuple[bytes, ...]], ...] = (
    (".pdf", _PDF),
    (".png", _PNG),
    (".jpg", _JPEG),
    (".jpeg", _JPEG),
)

# Image-only set for signature / acknowledgment captures.
_IMAGE_ONLY: tuple[tuple[str, tuple[bytes, ...]], ...] = (
    (".png", _PNG),
    (".jpg", _JPEG),
    (".jpeg", _JPEG),
    (".gif", _GIF),
    (".webp", _WEBP),
)

# Lookup table keyed by category name. Centralised so the call sites
# only reference category strings, not the magic tables.
_CATEGORIES: dict[str, tuple[tuple[str, tuple[bytes, ...]], ...]] = {
    "case_attachment": _DOC_LIKE,
    "cheque_attachment": _DOC_LIKE,
    "transition_attachment": _DOC_LIKE,
    "signed_form": _SIGNED_FORM,
    "image": _IMAGE_ONLY,
    "physical_document": _DOC_LIKE,
}

# How many bytes to sniff. 12 covers every signature above (the longest
# is the legacy-Office OLE header at 8 bytes; WebP needs 12 to verify
# the "WEBP" subtype after the "RIFF" prefix).
_SNIFF_BYTES = 12


def _read_head(upload: UploadFile) -> bytes:
    head = upload.file.read(_SNIFF_BYTES)
    # Rewind so the streaming write that follows reads from byte 0.
    try:
        upload.file.seek(0)
    except (AttributeError, OSError):
        pass
    return head


def _magic_matches(head: bytes, prefixes: Iterable[bytes]) -> bool:
    for p in prefixes:
        if head.startswith(p):
            # WebP is "RIFF" + size + "WEBP" — extra check.
            if p == b"RIFF" and head[8:12] != b"WEBP":
                continue
            return True
    return False


def validate_upload(upload: UploadFile, category: str) -> None:
    """Reject the upload if extension OR magic bytes don't match the
    allowlist for ``category``. Empty files are also rejected.

    Raises ``HTTPException(415)`` on type mismatch.
    """
    table = _CATEGORIES.get(category)
    if table is None:
        # Defensive default: no constraint. Categories not in the map
        # are server-internal categories (signatures get their own
        # check in storage.save_user_signature) so we don't block them.
        return

    name = (upload.filename or "").strip()
    ext = Path(name).suffix.lower()
    head = _read_head(upload)

    if not head:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Uploaded file is empty.",
        )

    for allowed_ext, prefixes in table:
        if ext == allowed_ext and _magic_matches(head, prefixes):
            return

    allowed = ", ".join(sorted({e for e, _ in table}))
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            f"File type not allowed for this upload. "
            f"Allowed extensions: {allowed}. "
            "The file's contents must also match its extension."
        ),
    )
