"""Authentication request/response schemas."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    # Plain str (not EmailStr) so internal / .local addresses like
    # admin@pug.local can sign in. Real-email validation happens at
    # user-create time, not at login.
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    permissions: list[str]
    is_super: bool
    divisions: list[int]
