"""Authentication request/response schemas."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Plain str (not EmailStr) so internal / .local addresses like
    # admin@pug.local can sign in. Real-email validation happens at
    # user-create time, not at login.
    email: str
    password: str
    totp_code: str | None = None


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
    totp_enabled: bool = False
    has_signature: bool = False
    locale: str = "en"


class LocaleUpdateRequest(BaseModel):
    locale: str = Field(pattern="^(en|ar)$")


class TotpEnrollResponse(BaseModel):
    secret: str
    otpauth_url: str
    qr_data_url: str


class TotpVerifyRequest(BaseModel):
    code: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class CapabilitiesResponse(BaseModel):
    """Role-driven UI capability bundle consumed by the frontend
    (see ``app/core/permissions.py::ROLE_CAPABILITIES``)."""

    role: str
    is_super: bool
    menus: list[str]
    actions: list[str]
    scope: str
    divisions: list[int]
