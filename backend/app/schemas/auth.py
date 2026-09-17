from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.core.security import password_strength_errors
from app.schemas.common import ApiModel


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(ApiModel):
    refresh_token: str


class RoleOut(ApiModel):
    name: str
    label: str
    description: str
    permissions: list[str]


class UserOut(ApiModel):
    id: str
    email: EmailStr
    full_name: str
    role_name: str
    role_label: str | None = None
    job_title: str | None = None
    team: str | None = None
    is_active: bool
    must_change_password: bool = False
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    permissions: list[str] = []
    initials: str | None = None


class TokenResponse(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class ChangePasswordRequest(ApiModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v: str) -> str:
        errors = password_strength_errors(v)
        if errors:
            raise ValueError(" ".join(errors))
        return v


class UserCreate(ApiModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role_name: str
    password: str
    job_title: str | None = None
    team: str | None = None

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        errors = password_strength_errors(v)
        if errors:
            raise ValueError(" ".join(errors))
        return v


class UserUpdate(ApiModel):
    full_name: str | None = Field(default=None, max_length=160)
    role_name: str | None = None
    job_title: str | None = None
    team: str | None = None
    is_active: bool | None = None
    reset_password: str | None = None
