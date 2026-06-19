"""In-app notification endpoints (bell)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationRead, UnreadCount

router = APIRouter(prefix="/notifications", tags=["notifications"])


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
