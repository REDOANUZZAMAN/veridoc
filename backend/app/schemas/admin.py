from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import ApiModel


class RuleOut(ApiModel):
    id: str
    code: str
    name: str
    category: str
    description: str
    default_severity: str
    weight: float
    enabled: bool
    applies_to: list[str] = []
    params: dict = {}
    version: str
    is_system: bool
    updated_at: datetime


class RuleUpdate(ApiModel):
    enabled: bool | None = None
    default_severity: str | None = Field(default=None,
                                         pattern="^(info|low|medium|high|critical)$")
    weight: float | None = Field(default=None, ge=0, le=60)
    params: dict | None = None


class ProviderOut(ApiModel):
    id: str
    kind: str
    key: str
    label: str
    description: str
    is_active: bool
    is_demo: bool
    credential_env_keys: list[str] = []
    settings_json: dict = {}
    model_name: str | None = None
    model_version: str | None = None
    health_status: str
    health_detail: str | None = None
    updated_at: datetime


class ProviderUpdate(ApiModel):
    is_active: bool | None = None
    settings_json: dict | None = None
    model_name: str | None = Field(default=None, max_length=80)
    model_version: str | None = Field(default=None, max_length=40)


class SettingOut(ApiModel):
    key: str
    label: str
    value: Any
    description: str
    updated_at: datetime


class SettingUpdate(ApiModel):
    value: Any
