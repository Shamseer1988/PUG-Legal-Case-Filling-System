"""Saved report filter schemas (Phase 27)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SavedFilterBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    report_key: str = Field(min_length=1, max_length=50)
    params: dict[str, Any] = Field(default_factory=dict)
    is_public: bool = False


class SavedFilterCreate(SavedFilterBase):
    pass


class SavedFilterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    params: dict[str, Any] | None = None
    is_public: bool | None = None


class SavedFilterRead(SavedFilterBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_by_id: int
    created_by_name: str = ""
    is_mine: bool = False
    created_at: datetime
    updated_at: datetime
