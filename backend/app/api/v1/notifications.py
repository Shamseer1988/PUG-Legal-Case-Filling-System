"""In-app notification endpoints (bell + SSE stream)."""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import decode_token
from app.db import session as _session_mod
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationRead, UnreadCount

router = APIRouter(prefix="/notifications", tags=["notifications"])

# SSE tuning. Long-poll interval = how often the worker checks the
# DB for new notifications. Keepalive = how often we emit a ``ping``
# comment line so proxies (and the browser) don't drop the socket.
SSE_POLL_SECONDS = 5
SSE_KEEPALIVE_SECONDS = 25
# Maximum lifetime of a single connection. EventSource auto-reconnects,
# so we cap each socket to keep DB connection pools healthy.
SSE_MAX_LIFETIME_SECONDS = 60 * 30


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    only_unread: bool = False,
    limit: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationRead]:
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if only_unread:
        q = q.filter(Notification.is_read.is_(False))
    rows = q.order_by(Notification.id.desc()).limit(min(limit, 200)).all()
    return [NotificationRead.model_validate(r) for r in rows]


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UnreadCount:
    n = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.is_read.is_(False))
        .count()
    )
    return UnreadCount(unread=n)


@router.post("/{nid}/read", response_model=NotificationRead)
def mark_read(
    nid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(n)
    return NotificationRead.model_validate(n)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read.is_(False)
    ).update({"is_read": True, "read_at": datetime.now(timezone.utc)})
    db.commit()


# ---------------------------------------------------------------------------
# Server-Sent Events stream (Phase 26)
# ---------------------------------------------------------------------------
def _resolve_stream_user(ticket: str) -> int:
    """Validate the short-lived stream ticket. Raises HTTPException
    with 401 on any failure."""
    try:
        payload = decode_token(ticket)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid ticket: {e}") from e
    if payload.get("type") != "stream":
        raise HTTPException(status_code=401, detail="Wrong ticket type")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Malformed ticket")
    try:
        return int(sub)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=401, detail="Bad ticket subject") from e


def _sse(event: str | None, data: dict | str) -> str:
    """Format an SSE frame.

    Always ends with ``\\n\\n`` so the browser flushes immediately.
    """
    if isinstance(data, dict):
        data = json.dumps(data)
    parts: list[str] = []
    if event:
        parts.append(f"event: {event}")
    for line in str(data).splitlines() or [""]:
        parts.append(f"data: {line}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)


@router.get("/stream")
async def stream_notifications(
    request: Request,
    ticket: str = Query(..., description="Short-lived JWT from /auth/stream-ticket"),
) -> StreamingResponse:
    """Server-Sent Events stream of new notifications for the user.

    Replaces the 30-second poll the NotificationBell used to do.
    Auth via a short-lived ticket (the browser's EventSource API
    can't set custom headers, so a query-string token is the
    standard pattern).

    Events emitted:
      - ``hello`` once, on connect — payload ``{"unread": <count>}``
      - ``notification`` per new row — full NotificationRead payload
      - ``ping`` ~every 25s as a keepalive comment line

    The connection has a hard 30-minute lifetime; EventSource will
    auto-reconnect with a fresh ticket on the client side.
    """
    user_id = _resolve_stream_user(ticket)

    async def generator():
        # Each connection owns its own DB session so commits made
        # elsewhere become visible on the next poll. Resolve
        # SessionLocal via the module attribute so test fixtures
        # that swap it in get respected.
        db = _session_mod.SessionLocal()
        try:
            # Discover the last existing id + send the initial
            # unread count as a hello event so the bell can paint
            # without an extra HTTP round-trip.
            last_id = (
                db.query(Notification.id)
                .filter(Notification.user_id == user_id)
                .order_by(Notification.id.desc())
                .limit(1)
                .scalar()
                or 0
            )
            unread = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.is_read.is_(False),
                )
                .count()
            )
            yield _sse("hello", {"unread": int(unread), "last_id": int(last_id)})

            start = datetime.now(timezone.utc)
            seconds_since_keepalive = 0
            while True:
                if await request.is_disconnected():
                    break
                age = (datetime.now(timezone.utc) - start).total_seconds()
                if age >= SSE_MAX_LIFETIME_SECONDS:
                    # Tell the client to reconnect cleanly. EventSource
                    # auto-retries; we just close the socket.
                    yield _sse("bye", {"reason": "max_lifetime"})
                    break

                # Pick up anything new since last_id.
                fresh = (
                    db.query(Notification)
                    .filter(
                        Notification.user_id == user_id,
                        Notification.id > last_id,
                    )
                    .order_by(Notification.id.asc())
                    .limit(50)
                    .all()
                )
                if fresh:
                    for n in fresh:
                        yield _sse(
                            "notification",
                            NotificationRead.model_validate(n).model_dump(mode="json"),
                        )
                    last_id = fresh[-1].id
                    # Re-send unread count so the badge is always fresh
                    unread = (
                        db.query(Notification)
                        .filter(
                            Notification.user_id == user_id,
                            Notification.is_read.is_(False),
                        )
                        .count()
                    )
                    yield _sse("unread", {"unread": int(unread)})

                await asyncio.sleep(SSE_POLL_SECONDS)
                seconds_since_keepalive += SSE_POLL_SECONDS
                if seconds_since_keepalive >= SSE_KEEPALIVE_SECONDS:
                    seconds_since_keepalive = 0
                    # Comment line: keeps proxies + the browser happy
                    # without firing a JS-side event.
                    yield ": keepalive\n\n"
        finally:
            db.close()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
