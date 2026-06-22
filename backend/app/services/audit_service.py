"""Append-only audit log with a SHA-256 hash chain.

Every recorded event chains to the previous row via ``prev_hash``; the
row's own ``row_hash`` is computed over (prev_hash + canonical payload).
``verify_chain`` walks the table in id order and recomputes the chain,
returning any broken links.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import request_context
from app.models.audit import AuditLog
from app.models.user import User

# ---- Action constants ----
ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"
ACTION_LOGIN = "login"
ACTION_LOGIN_FAILED = "login_failed"
ACTION_LOGOUT = "logout"
ACTION_TRANSITION = "transition"
ACTION_SUBMIT = "submit"
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"
ACTION_CLARIFY = "clarification_requested"
ACTION_RESUBMIT = "resubmit"
ACTION_PERMISSION_CHANGE = "permission_change"
ACTION_BACKUP = "backup"
ACTION_RESTORE = "restore"


def _canonical(d: dict[str, Any]) -> str:
    return json.dumps(d, sort_keys=True, default=str, separators=(",", ":"))


def _compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(_canonical(payload).encode("utf-8"))
    return h.hexdigest()


def _hash_payload(row: AuditLog) -> dict[str, Any]:
    # SQLite drops tzinfo on round-trip while Postgres preserves it.
    # Normalise to a tz-aware UTC ISO string so the hash computed at
    # insert-time matches the hash recomputed by verify_chain on any
    # backend.
    ts = row.created_at
    if ts is not None and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return {
        "created_at": ts.isoformat() if ts else "",
        "actor_id": row.actor_id,
        "actor_email": row.actor_email,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "summary": row.summary,
        "before": row.before or {},
        "after": row.after or {},
        "meta": row.meta or {},
    }


def diff_dicts(before: dict, after: dict) -> tuple[dict, dict]:
    """Return only the keys that differ between before and after."""
    keys = set(before) | set(after)
    b: dict = {}
    a: dict = {}
    for k in keys:
        bv = before.get(k)
        av = after.get(k)
        if bv != av:
            b[k] = bv
            a[k] = av
    return b, a


def record_event(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    summary: str = "",
    before: dict | None = None,
    after: dict | None = None,
    meta: dict | None = None,
    actor: User | None = None,
    commit: bool = False,
) -> AuditLog:
    """Append a single audit row. Caller is responsible for commit unless
    ``commit=True`` is passed."""
    ctx = request_context.get_ctx()
    actor_id: int | None = None
    actor_email = ""
    actor_role = ""
    if actor is not None:
        actor_id = actor.id
        actor_email = actor.email
        actor_role = actor.role.name if actor.role else ""
    elif ctx is not None:
        actor_id = ctx.user_id
        actor_email = ctx.user_email
        actor_role = ctx.user_role

    # Lock the tail of the chain so concurrent writers serialise.
    latest = (
        db.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(1).with_for_update()
        ).scalars().first()
    )
    prev_hash = latest.row_hash if latest else ""

    row = AuditLog(
        created_at=datetime.now(timezone.utc),
        actor_id=actor_id,
        actor_email=actor_email,
        actor_role=actor_role,
        ip_address=(ctx.ip if ctx else "")[:45],
        user_agent=(ctx.user_agent if ctx else "")[:500],
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary[:500],
        before=before or {},
        after=after or {},
        meta=meta or {},
        prev_hash=prev_hash,
    )
    row.row_hash = _compute_hash(prev_hash, _hash_payload(row))
    db.add(row)
    db.flush()
    if commit:
        db.commit()
    return row


# ----- Convenience wrappers used by callers -----
def audit_create(
    db: Session,
    entity_type: str,
    entity_id: int,
    summary: str,
    after: dict,
    *,
    commit: bool = False,
) -> AuditLog:
    return record_event(
        db,
        action=ACTION_CREATE,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        after=after,
        commit=commit,
    )


def audit_update(
    db: Session,
    entity_type: str,
    entity_id: int,
    summary: str,
    before: dict,
    after: dict,
    *,
    commit: bool = False,
) -> AuditLog:
    b, a = diff_dicts(before, after)
    return record_event(
        db,
        action=ACTION_UPDATE,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        before=b,
        after=a,
        commit=commit,
    )


def audit_delete(
    db: Session,
    entity_type: str,
    entity_id: int,
    summary: str,
    before: dict,
    *,
    commit: bool = False,
) -> AuditLog:
    return record_event(
        db,
        action=ACTION_DELETE,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        before=before,
        commit=commit,
    )


# ----- Verify -----
def verify_chain(db: Session) -> dict[str, Any]:
    """Walk every row in id order and recompute the chain."""
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    issues: list[dict[str, Any]] = []
    prev_hash = ""
    for r in rows:
        expected = _compute_hash(prev_hash, _hash_payload(r))
        if r.prev_hash != prev_hash:
            issues.append({"id": r.id, "issue": "prev_hash_mismatch"})
        if r.row_hash != expected:
            issues.append({"id": r.id, "issue": "row_hash_mismatch"})
        prev_hash = r.row_hash
    return {
        "verified": not issues,
        "count": len(rows),
        "issues": issues,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ----- Helpers for snapshotting SQLAlchemy models -----
_HIDE = {"password_hash"}


def snapshot(obj: Any, fields: list[str] | None = None) -> dict:
    """Return a dict suitable for the ``before`` / ``after`` columns.

    Internal fields like ``password_hash`` are scrubbed; values are coerced
    via ``str`` so they round-trip through JSON.
    """
    out: dict = {}
    if obj is None:
        return out
    if fields is None:
        try:
            fields = [c.key for c in obj.__table__.columns]  # type: ignore[attr-defined]
        except Exception:
            return out
    for f in fields:
        if f in _HIDE:
            continue
        v = getattr(obj, f, None)
        if v is None or isinstance(v, (str, int, float, bool)):
            out[f] = v
        else:
            out[f] = str(v)
    return out
