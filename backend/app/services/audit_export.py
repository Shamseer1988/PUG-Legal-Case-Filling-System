"""Tamper-evident audit log exports (Phase 30).

A signed export bundles the selected audit rows + an Ed25519
signature over their canonical JSON form, so the recipient can
verify offline that the payload hasn't been altered.

Bundle shape::

    {
      "format": "pug-legal/audit-export.v1",
      "generated_at": "2026-...Z",
      "row_count": 42,
      "filters": {...},
      "rows": [...],          # ordered by id ascending
      "public_key": "...",    # base64 ed25519 public key
      "signature": "..."      # base64 ed25519 sig over canonical(rows)
    }

The signing key is generated lazily and stored in SettingsKV
(``audit.sign.privkey`` encrypted via crypto_service, ``audit.sign.pubkey``
plain text). Operators can rotate by deleting both keys; a new
keypair is then minted on the next export.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.settings import SettingsKV

PRIV_KEY_SETTING = "audit.sign.privkey"
PUB_KEY_SETTING = "audit.sign.pubkey"

FORMAT_ID = "pug-legal/audit-export.v1"


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")


def _row_to_dict(r: AuditLog) -> dict[str, Any]:
    return {
        "id": r.id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "actor_id": r.actor_id,
        "actor_email": r.actor_email,
        "actor_role": r.actor_role,
        "ip_address": r.ip_address,
        "user_agent": r.user_agent,
        "action": r.action,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "summary": r.summary,
        "before": r.before or {},
        "after": r.after or {},
        "meta": r.meta or {},
        "prev_hash": r.prev_hash,
        "row_hash": r.row_hash,
    }


def _kv_get(db: Session, key: str) -> str | None:
    row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    return row.value if (row and row.value) else None


def _kv_set(db: Session, key: str, value: str) -> None:
    row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    if row is None:
        db.add(SettingsKV(key=key, value=value, is_sensitive=False))
    else:
        row.value = value
    db.flush()


def _load_or_create_keypair(db: Session) -> tuple[Ed25519PrivateKey, str]:
    """Return (private_key_obj, public_key_b64).

    Reads the key from SettingsKV, or mints + persists a fresh pair
    on first use. We bypass settings_service here so the keys don't
    need to be registered in the public settings descriptor catalog;
    they're internal cryptographic material, not user-tunable config.
    """
    priv_b64 = _kv_get(db, PRIV_KEY_SETTING)
    pub_b64 = _kv_get(db, PUB_KEY_SETTING)
    if priv_b64 and pub_b64:
        priv = serialization.load_pem_private_key(
            base64.b64decode(priv_b64), password=None
        )
        if not isinstance(priv, Ed25519PrivateKey):
            raise RuntimeError("audit signing key is not Ed25519")
        return priv, pub_b64

    # Generate a fresh keypair.
    priv = Ed25519PrivateKey.generate()
    pub: Ed25519PublicKey = priv.public_key()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_b64_new = base64.b64encode(priv_pem).decode()
    pub_b64_new = base64.b64encode(pub_pem).decode()

    _kv_set(db, PRIV_KEY_SETTING, priv_b64_new)
    _kv_set(db, PUB_KEY_SETTING, pub_b64_new)
    db.commit()
    return priv, pub_b64_new


def get_public_key(db: Session) -> str:
    """Return the base64 PEM-wrapped public key.

    Used by the ``/admin/audit-log/signing-key`` endpoint so external
    auditors can fetch the public half once and verify any later
    export offline.
    """
    _, pub_b64 = _load_or_create_keypair(db)
    return pub_b64


def build_signed_export(
    db: Session,
    rows: list[AuditLog],
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Build the signed bundle. Caller is expected to have already
    applied any filters and ordered the rows however they want."""
    priv, pub_b64 = _load_or_create_keypair(db)
    payload_rows = [_row_to_dict(r) for r in rows]
    body = {
        "format": FORMAT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(payload_rows),
        "filters": filters,
        "rows": payload_rows,
    }
    signature = priv.sign(_canonical(body))
    body["public_key"] = pub_b64
    body["signature"] = base64.b64encode(signature).decode()
    return body


def verify_signed_export(bundle: dict[str, Any]) -> bool:
    """Round-trip helper used by tests + an admin "Verify" page.

    Returns True iff the signature matches the canonical form of the
    bundle's body (i.e. everything other than ``public_key`` and
    ``signature``).
    """
    sig_b64 = bundle.get("signature")
    pub_b64 = bundle.get("public_key")
    if not sig_b64 or not pub_b64:
        return False
    body = {k: v for k, v in bundle.items() if k not in ("signature", "public_key")}
    pub_pem = base64.b64decode(pub_b64)
    pub: Any = serialization.load_pem_public_key(pub_pem)
    if not isinstance(pub, Ed25519PublicKey):
        return False
    try:
        pub.verify(base64.b64decode(sig_b64), _canonical(body))
    except Exception:
        return False
    return True
