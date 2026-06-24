"""Seed default roles, admin user and minimal sample masters.

Idempotent: re-running will not duplicate rows.
"""

import os

from loguru import logger
from sqlalchemy.orm import Session

from app.core.permissions import ROLE_PRESETS
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.masters import Bank, CaseType, Division
from app.models.user import Role, User

DEFAULT_ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@pug.local")
DEFAULT_ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "Admin@123")


def seed_roles(db: Session) -> dict[str, Role]:
    out: dict[str, Role] = {}
    for name, perms in ROLE_PRESETS.items():
        role = db.query(Role).filter(Role.name == name).first()
        if not role:
            role = Role(name=name, permissions=list(perms), is_system=True)
            db.add(role)
            db.flush()
            logger.info(f"Created role: {name}")
        else:
            # keep permissions up to date but do not overwrite manual edits to non-system roles
            if role.is_system:
                role.permissions = list(perms)
        out[name] = role
    db.commit()
    return out


def seed_admin(db: Session, admin_role: Role) -> User:
    user = db.query(User).filter(User.email == DEFAULT_ADMIN_EMAIL).first()
    if user:
        return user
    user = User(
        email=DEFAULT_ADMIN_EMAIL,
        full_name="System Administrator",
        password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        role_id=admin_role.id,
        is_active=True,
        is_super=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"Created admin user: {DEFAULT_ADMIN_EMAIL}")
    return user


def seed_sample_masters(db: Session) -> None:
    samples = [
        (Division, "code", [
            {"code": "HO", "name": "Head Office", "address": "Paris United Group HQ"},
            {"code": "RET", "name": "Retail Division"},
            {"code": "DIST", "name": "Distribution Division"},
        ]),
        (Bank, "code", [
            {"code": "ENBD", "name": "Emirates NBD"},
            {"code": "FAB", "name": "First Abu Dhabi Bank"},
            {"code": "ADCB", "name": "Abu Dhabi Commercial Bank"},
        ]),
        (CaseType, "code", [
            {"code": "CRIM", "name": "Criminal"},
            {"code": "CIV", "name": "Civil"},
            {"code": "BOTH", "name": "Criminal + Civil"},
        ]),
    ]
    for model, unique_field, rows in samples:
        for row in rows:
            if not db.query(model).filter(getattr(model, unique_field) == row[unique_field]).first():
                db.add(model(**row))
    db.commit()


def run_seed() -> None:
    db = SessionLocal()
    try:
        roles = seed_roles(db)
        seed_admin(db, roles["Admin"])
        seed_sample_masters(db)
        logger.info("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
