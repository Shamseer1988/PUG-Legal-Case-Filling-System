"""Web Push delivery (Phase 32).

A subscription is persisted per (user, device endpoint). When the
app wants to push a notification, ``send_to_user`` iterates the
user's active subscriptions and calls into ``pywebpush`` if it's
installed. If not (some platforms can't build its ``http-ece``
dep), we log the would-be push so operators can verify the
pipeline and later wire FCM / APNs or fix the build.

The VAPID keypair is generated lazily on first use and stored in
settings_kv. Rotation is a manual delete + restart.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    EllipticCurvePrivateKey,
    generate_private_key,
)
from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.push import PushSubscription
from app.models.settings import SettingsKV

VAPID_PRIV_KEY = "push.vapid.privkey"
VAPID_PUB_KEY = "push.vapid.pubkey"
VAPID_SUBJECT_KEY = "push.vapid.subject"


def _kv_get(db: Session, key: str) -> str | None:
    row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    return row.value if (row and row.value) else None


def _kv_set(db: Session, key: str, value: str) -> None:
    row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    if row is None:
        db.add(SettingsKV(key=key, value=value, is_sensitive=False))
    else:
        row.value = value


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _ensure_vapid(db: Session) -> tuple[str, str, str]:
    """Return (private_pem_b64, public_b64url_raw, subject).

    Public is encoded the way the Web Push spec expects: the raw
    uncompressed P-256 point (65 bytes starting 0x04) in
    base64url-no-padding. Private is PEM PKCS8 base64 because we
    only ever consume it again via the cryptography lib.
    """
    priv_b64 = _kv_get(db, VAPID_PRIV_KEY)
    pub_b64 = _kv_get(db, VAPID_PUB_KEY)
    subject = _kv_get(db, VAPID_SUBJECT_KEY) or (
        f"mailto:{settings.smtp_from_email or 'no-reply@pug.local'}"
    )
    if priv_b64 and pub_b64:
        return priv_b64, pub_b64, subject

    priv: EllipticCurvePrivateKey = generate_private_key(SECP256R1())
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    priv_b64_new = base64.b64encode(priv_pem).decode()
    pub_b64_new = _b64url(pub_raw)
    _kv_set(db, VAPID_PRIV_KEY, priv_b64_new)
    _kv_set(db, VAPID_PUB_KEY, pub_b64_new)
    _kv_set(db, VAPID_SUBJECT_KEY, subject)
    db.commit()
    return priv_b64_new, pub_b64_new, subject


def get_public_key(db: Session) -> str:
    """The base64url-no-padding raw public key the browser passes
    to ``pushManager.subscribe({applicationServerKey})``."""
    _, pub_b64, _ = _ensure_vapid(db)
    return pub_b64


# ---------------------------------------------------------------------------
# Subscription storage
# ---------------------------------------------------------------------------
def upsert_subscription(
    db: Session,
    *,
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str = "",
) -> PushSubscription:
    """Insert / replace a subscription. Same endpoint from the same
    browser only ever results in one row; if the user re-subscribes
    on a different device, that gets its own row."""
    row = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == endpoint)
        .first()
    )
    if row:
        row.user_id = user_id
        row.p256dh = p256dh
        row.auth = auth
        row.user_agent = user_agent[:500]
    else:
        row = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=user_agent[:500],
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_subscription(db: Session, *, user_id: int, endpoint: str) -> int:
    n = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint == endpoint,
        )
        .delete()
    )
    db.commit()
    return int(n)


def list_subscriptions(db: Session, user_id: int) -> list[PushSubscription]:
    return (
        db.query(PushSubscription)
        .filter(PushSubscription.user_id == user_id)
        .order_by(PushSubscription.id.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------
def _try_send_one(
    sub: PushSubscription,
    payload: dict[str, Any],
    priv_b64: str,
    subject: str,
) -> tuple[bool, str]:
    """Best-effort send via pywebpush if installed.

    Returns (ok, detail). When pywebpush isn't installed we log the
    would-be push and report ``ok=True`` with detail="logged" so
    callers can still surface a useful state in tests + UI."""
    try:
        from pywebpush import WebPushException, webpush  # type: ignore
    except Exception:  # pragma: no cover - depends on host build
        logger.info(
            "[push/log-only] endpoint={} payload={}",
            sub.endpoint[:80],
            payload,
        )
        return True, "logged"

    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=base64.b64decode(priv_b64).decode(),
            vapid_claims={"sub": subject},
        )
    except WebPushException as e:  # pragma: no cover - integration
        code = getattr(e.response, "status_code", None) if e.response is not None else None
        return False, f"WebPushException {code}: {e}"
    except Exception as e:  # pragma: no cover - integration
        return False, f"{type(e).__name__}: {e}"
    return True, "sent"


def send_to_user(db: Session, *, user_id: int, payload: dict[str, Any]) -> dict[str, int]:
    """Push to every endpoint registered by ``user_id``.

    Cleans up subscriptions that the gateway has rejected with a
    410 (Gone) so a stale device doesn't keep failing on every
    notification.
    """
    subs = list_subscriptions(db, user_id)
    if not subs:
        return {"sent": 0, "failed": 0, "gone": 0}

    priv_b64, _pub, subject = _ensure_vapid(db)
    stats = {"sent": 0, "failed": 0, "gone": 0}
    now = datetime.now(timezone.utc)
    for sub in subs:
        ok, detail = _try_send_one(sub, payload, priv_b64, subject)
        if ok:
            stats["sent"] += 1
            sub.last_used_at = now
        elif "410" in detail:
            stats["gone"] += 1
            db.delete(sub)
        else:
            stats["failed"] += 1
            logger.warning(
                "push to {} failed: {}", sub.endpoint[:80], detail
            )
    db.commit()
    return stats
