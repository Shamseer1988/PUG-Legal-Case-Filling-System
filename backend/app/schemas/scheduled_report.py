"""Scheduled-report schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScheduledReportBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    report_key: str = Field(min_length=1, max_length=50)
    params: dict[str, Any] = Field(default_factory=dict)
    cron: str = Field(min_length=1, max_length=50)
    timezone: str = "UTC"
    recipients: list[str] = []
    cc: list[str] = []
    bcc: list[str] = []
    formats: list[str] = Field(default_factory=lambda: ["pdf"])
    notes: str = ""


class ScheduledReportCreate(ScheduledReportBase):
    pass


class ScheduledReportUpdate(BaseModel):
    name: str | None = None
    report_key: str | None = None
    params: dict[str, Any] | None = None
    cron: str | None = None
    timezone: str | None = None
    recipients: list[str] | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None
    formats: list[str] | None = None
    notes: str | None = None
    is_active: bool | None = None


class ScheduledReportRead(ScheduledReportBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    last_run_at: datetime | None
    last_run_status: str
    last_run_error: str
    next_run_at: datetime | None
    created_by_id: int
    created_at: datetime


class ScheduledReportRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    schedule_id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    rows_count: int
    error: str
    email_log_id: int | None
