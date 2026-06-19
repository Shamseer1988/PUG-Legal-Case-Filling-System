"""Persisted application settings with encryption-at-rest for sensitive
values.

DB values override env vars when present and non-empty. Sensitive values
are stored as ``ENC:<base64>`` where the bytes are an AES-256-GCM envelope
(reuses the Phase 9 ``crypto_service``).
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.models.settings import ENCRYPTION_PREFIX, SettingsKV
from app.services import crypto_service
from app.services.settings_descriptors import GROUPS, field_for

MASKED = "********"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------- encryption helpers ----------------
def _encrypt(raw: str) -> str:
    blob = crypto_service.encrypt_bytes(raw.encode("utf-8"))
    return ENCRYPTION_PREFIX + base64.b64encode(blob).decode()


def _decrypt(stored: str) -> str:
    if not stored.startswith(ENCRYPTION_PREFIX):
        return stored
    blob = base64.b64decode(stored[len(ENCRYPTION_PREFIX) :])
    return crypto_service.decrypt_bytes(blob).decode("utf-8")


# ---------------- raw get/set ----------------
def _row(db: Session, key: str) -> SettingsKV | None:
    return db.query(SettingsKV).filter(SettingsKV.key == key).first()


def _env_fallback(key: str) -> str | None:
    f = field_for(key)
    if not f:
        return None
    env_name = f.get("env")
    if not env_name:
        return None
    v = os.environ.get(env_name)
    return v


def get_raw(db: Session, key: str) -> str | None:
    """Return the persisted (and decrypted) value, falling back to env."""
    row = _row(db, key)
    if row and row.value:
        try:
            return _decrypt(row.value)
        except Exception:
            return None
    env_v = _env_fallback(key)
    if env_v not in (None, ""):
        return env_v
    f = field_for(key)
    if f and "default" in f:
        d = f["default"]
        return str(d) if not isinstance(d, bool) else ("true" if d else "false")
    return None


def get_str(db: Session, key: str, default: str = "") -> str:
    v = get_raw(db, key)
    return v if v is not None else default


def get_int(db: Session, key: str, default: int = 0) -> int:
    v = get_raw(db, key)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def get_bool(db: Session, key: str, default: bool = False) -> bool:
    v = get_raw(db, key)
    if v is None or v == "":
        return default
    return v.lower() in ("1", "true", "yes", "on")


def set_value(
    db: Session,
    key: str,
    value: str,
    *,
    user_id: int | None = None,
) -> SettingsKV:
    f = field_for(key)
    if not f:
        raise ValueError(f"Unknown settings key: {key}")
    is_sensitive = bool(f.get("sensitive"))
    stored = _encrypt(value) if (is_sensitive and value) else value
    row = _row(db, key)
    if row is None:
        row = SettingsKV(
            key=key,
            value=stored,
            is_sensitive=is_sensitive,
            updated_by_id=user_id,
            updated_at_explicit=_utcnow(),
        )
        db.add(row)
    else:
        row.value = stored
        row.is_sensitive = is_sensitive
        row.updated_by_id = user_id
        row.updated_at_explicit = _utcnow()
    db.flush()
    return row


# ---------------- group helpers ----------------
def get_group(db: Session, group_key: str, *, unmask: bool = False) -> dict[str, Any]:
    """Return current values for every field in the group.

    Sensitive values are masked unless ``unmask=True``. A separate
    ``"_meta"`` key carries (source, has_value) per field.
    """
    out: dict[str, Any] = {}
    meta: dict[str, dict[str, Any]] = {}
    for g in GROUPS:
        if g["key"] != group_key:
            continue
        for f in g["fields"]:
            key = f["key"]
            row = _row(db, key)
            raw = ""
            source = "default"
            if row and row.value:
                try:
                    raw = _decrypt(row.value)
                    source = "db"
                except Exception:
                    raw = ""
            elif _env_fallback(key) not in (None, ""):
                raw = _env_fallback(key) or ""
                source = "env"
            elif "default" in f:
                raw = (
                    "true"
                    if (isinstance(f["default"], bool) and f["default"])
                    else "false"
                    if isinstance(f["default"], bool)
                    else str(f["default"])
                )

            display: Any = raw
            if f["type"] == "checkbox":
                display = raw.lower() in ("1", "true", "yes", "on")
            elif f["type"] == "number":
                try:
                    display = int(raw) if raw not in (None, "") else None
                except (TypeError, ValueError):
                    display = None

            if f.get("sensitive") and not unmask:
                # Mask sensitive non-empty values
                display = MASKED if raw else ""

            out[key] = display
            meta[key] = {"source": source, "has_value": bool(raw)}
        out["_meta"] = meta
        return out
    raise ValueError(f"Unknown settings group: {group_key}")


def set_group(
    db: Session,
    group_key: str,
    values: dict[str, Any],
    *,
    user_id: int | None,
) -> dict[str, Any]:
    """Apply a partial map of changes. Empty string clears the row;
    the literal ``********`` mask is treated as 'no change'."""
    for g in GROUPS:
        if g["key"] != group_key:
            continue
        valid_keys = {f["key"] for f in g["fields"]}
        for k, v in values.items():
            if k not in valid_keys:
                raise ValueError(f"Unknown field for group {group_key}: {k}")
            f = next(field_for(k) for _ in [0]) or field_for(k)
            assert f is not None
            if v is None:
                # Skip
                continue
            if isinstance(v, bool):
                v_str = "true" if v else "false"
            else:
                v_str = str(v)
            if f.get("sensitive") and v_str == MASKED:
                continue  # leave existing encrypted value alone
            if v_str == "" and not f.get("sensitive"):
                # Clear the value
                set_value(db, k, "", user_id=user_id)
            else:
                set_value(db, k, v_str, user_id=user_id)
        db.commit()
        return get_group(db, group_key)
    raise ValueError(f"Unknown settings group: {group_key}")


# ---------------- SMTP runtime override ----------------
def effective_smtp(db: Session) -> dict[str, Any]:
    return {
        "host": get_str(db, "smtp.host", app_settings.smtp_host),
        "port": get_int(db, "smtp.port", app_settings.smtp_port),
        "use_tls": get_bool(db, "smtp.use_tls", app_settings.smtp_use_tls),
        "username": get_str(db, "smtp.username", app_settings.smtp_username),
        "password": get_str(db, "smtp.password", app_settings.smtp_password),
        "from_email": get_str(db, "smtp.from_email", app_settings.smtp_from_email),
        "from_name": get_str(db, "smtp.from_name", app_settings.smtp_from_name),
    }
