"""User and Role schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RoleBase(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = ""
    permissions: list[str] = []


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


class RoleRead(RoleBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_system: bool


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role_id: int
    is_active: bool = True
    is_super: bool = False


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    division_ids: list[int] = []


class UserUpdate(BaseModel):
    full_name: str | None = None
    role_id: int | None = None
    is_active: bool | None = None
    is_super: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    division_ids: list[int] | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role_id: int
    role_name: str
    is_active: bool
    is_super: bool
    last_login_at: datetime | None
    division_ids: list[int]
