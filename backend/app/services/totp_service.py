"""TOTP enrolment + verification (RFC 6238)."""

from __future__ import annotations

import base64
import io
from datetime import datetime, timezone

import pyotp
import qrcode
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User

ISSUER = "PUG Legal CCS"


def begin_enrollment(db: Session, user: User) -> tuple[str, str, str]:
    """Generate a fresh secret. Persists it but leaves 2FA disabled until
    verified.

    Returns (secret, otpauth_url, qr_data_url).
    """
    secret = pyotp.random_base32()
    user.totp_secret = secret
    user.totp_enabled = False
    db.commit()
    db.refresh(user)
    otpauth = pyotp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name=ISSUER
    )
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(otpauth)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0b1020", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return secret, otpauth, data_url


def verify_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    try:
        return bool(pyotp.TOTP(secret).verify(code.strip(), valid_window=1))
    except Exception:
        return False


def activate(db: Session, user: User, code: str) -> bool:
    if not user.totp_secret:
        return False
    if not verify_code(user.totp_secret, code):
        return False
    user.totp_enabled = True
    user.totp_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return True


def disable(db: Session, user: User) -> None:
    user.totp_secret = ""
    user.totp_enabled = False
    user.totp_verified_at = None
    db.commit()


def check_login_code(user: User, code: str | None) -> bool:
    """Used during /auth/login - returns True if 2FA is satisfied for this
    user, False if a (valid) code is still required."""
    if not user.totp_enabled:
        return True
    return verify_code(user.totp_secret, code or "")
