"""AES-256-GCM envelope for backup files.

File format:
    8 bytes  - magic   "PUGBKP1\0"
    12 bytes - nonce   (cryptographically random per file)
    N bytes  - ciphertext including the 16-byte GCM tag at the end

The encryption key is read from ``settings.backup_encryption_key`` and
must be a base64-encoded 32-byte secret. If unset, encryption is
silently skipped (callers see ``is_encrypted=False``).
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

MAGIC = b"PUGBKP1\x00"
NONCE_LEN = 12


def get_key() -> bytes | None:
    raw = (settings.backup_encryption_key or "").strip()
    if not raw:
        return None
    try:
        key = base64.b64decode(raw)
    except Exception:
        return None
    if len(key) != 32:
        return None
    return key


def encryption_available() -> bool:
    return get_key() is not None


def encrypt_bytes(plaintext: bytes) -> bytes:
    key = get_key()
    if key is None:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY is not configured")
    nonce = os.urandom(NONCE_LEN)
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, plaintext, None)
    return MAGIC + nonce + ct


def decrypt_bytes(blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("Not an encrypted PUG backup file")
    key = get_key()
    if key is None:
        raise RuntimeError(
            "BACKUP_ENCRYPTION_KEY is not configured; cannot decrypt this backup"
        )
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_LEN]
    ct = blob[len(MAGIC) + NONCE_LEN :]
    aes = AESGCM(key)
    return aes.decrypt(nonce, ct, None)


def is_encrypted_blob(head: bytes) -> bool:
    return head.startswith(MAGIC)
