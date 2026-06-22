"""Web Push schemas (Phase 32)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1)
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)
    user_agent: str = ""


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1)


class PushSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    endpoint: str
    user_agent: str
    last_used_at: datetime | None
    created_at: datetime


class PushPublicKeyResponse(BaseModel):
    public_key: str
