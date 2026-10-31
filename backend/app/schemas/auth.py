"""Request/response schemas for authentication."""

from datetime import datetime

from pydantic import EmailStr, Field

from app.models.common import AppModel, PyObjectId
from app.models.enums import UserRole, UserStatus


class RegisterRequest(AppModel):
    """Self-service customer registration: creates a user and its customer record."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    company_name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=6, max_length=24)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    postal_code: str | None = Field(default=None, max_length=16)
    address_line1: str | None = Field(default=None, max_length=160)
    tax_id: str | None = Field(default=None, max_length=32)


class StaffCreateRequest(AppModel):
    """Manager-only creation of sales employee / manager accounts."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    role: UserRole
    phone: str | None = Field(default=None, max_length=24)


class LoginRequest(AppModel):
    email: EmailStr
    password: str


class RefreshRequest(AppModel):
    refresh_token: str


class ChangePasswordRequest(AppModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(AppModel):
    id: PyObjectId
    email: EmailStr
    full_name: str
    role: UserRole
    status: UserStatus
    phone: str | None = None
    customer_id: PyObjectId | None = None
    last_login_at: datetime | None = None
    created_at: datetime


class TokenResponse(AppModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
