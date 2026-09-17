from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class DetectionRule(Base, UUIDPrimaryKey, TimestampMixin):
    """Admin-tunable detector/rule catalogue.

    Both the consistency engine and the risk engine read severity + weight from
    here, so thresholds are configuration rather than code.
    """

    __tablename__ = "detection_rules"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    default_severity: Mapped[str] = mapped_column(String(16), default="medium")
    weight: Mapped[float] = mapped_column(Float, default=10.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    applies_to: Mapped[list] = mapped_column(JSONB, default=list)  # document types
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[str] = mapped_column(String(24), default="1.0.0")
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ProviderConfig(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "provider_configs"
    __table_args__ = (UniqueConstraint("kind", "key", name="uq_provider_configs_kind_key"),)

    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(48), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Never store secrets here - only the *name* of the env var that holds them.
    credential_env_keys: Mapped[list] = mapped_column(JSONB, default=list)
    settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    health_status: Mapped[str] = mapped_column(String(24), default="unknown")
    health_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SystemSetting(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(160), default="")
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
