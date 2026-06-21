"""Notification + email log schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    body: str
    link: str
    event: str
    related_case_id: int | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


class EmailLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    to_emails: str
    subject: str
    status: str
    attempts: int
    event: str
    related_case_id: int | None
    sent_at: datetime | None
    next_attempt_at: datetime | None = None
    last_attempted_at: datetime | None = None
    created_at: datetime
    error: str


class EmailLogDetail(EmailLogItem):
    cc_emails: str
    bcc_emails: str
    template_name: str
    body_html: str
    body_text: str
    related_user_id: int | None


class EmailBounceWebhook(BaseModel):
    email_log_id: int
    error: str


class TestEmailRequest(BaseModel):
    to_email: str


class TestEmailResponse(BaseModel):
    email_log_id: int
    status: str
    error: str
    sent_at: datetime | None
