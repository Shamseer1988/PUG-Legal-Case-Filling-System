"""Web Push subscription endpoints (Phase 32).

The browser:
1. Calls ``GET /push/vapid-public-key`` once.
2. Uses that key with ``serviceWorkerRegistration.pushManager.subscribe(...)``.
3. POSTs the resulting subscription back to ``/push/subscribe``.

When the backend wants to fire a push, ``push_service.send_to_user``
walks every subscription for the user and (if pywebpush is
available) signs + delivers; otherwise it logs.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.push import (
    PushPublicKeyResponse,
    PushSubscribeRequest,
    PushSubscriptionRead,
    PushUnsubscribeRequest,
)
from app.services import push_service

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/vapid-public-key", response_model=PushPublicKeyResponse)
def vapid_public_key(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PushPublicKeyResponse:
    """Return the VAPID public key (raw P-256 point, base64url
    no-padding) the browser needs to subscribe to push."""
    return PushPublicKeyResponse(public_key=push_service.get_public_key(db))


@router.post("/subscribe", response_model=PushSubscriptionRead)
def subscribe(
    payload: PushSubscribeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PushSubscriptionRead:
    row = push_service.upsert_subscription(
        db,
        user_id=user.id,
        endpoint=payload.endpoint,
        p256dh=payload.p256dh,
        auth=payload.auth,
        user_agent=payload.user_agent,
    )
    return PushSubscriptionRead.model_validate(row)


@router.post("/unsubscribe")
def unsubscribe(
    payload: PushUnsubscribeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    n = push_service.delete_subscription(
        db, user_id=user.id, endpoint=payload.endpoint
    )
    return {"removed": n}


@router.get("/subscriptions", response_model=list[PushSubscriptionRead])
def list_my_subscriptions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PushSubscriptionRead]:
    rows = push_service.list_subscriptions(db, user.id)
    return [PushSubscriptionRead.model_validate(r) for r in rows]
