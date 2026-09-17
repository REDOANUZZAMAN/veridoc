from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.enums import VerificationOutcome


class VerificationRequest(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "verification_requests"

    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    requested_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider_key: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    provider_label: Mapped[str] = mapped_column(String(120), nullable=False)
    # 'demo' when answers come from the bundled sample registry, 'production'
    # when a real insurer/government endpoint is configured.
    provider_mode: Mapped[str] = mapped_column(String(16), default="demo", nullable=False)
    request_type: Mapped[str] = mapped_column(String(48), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    trigger: Mapped[str] = mapped_column(String(24), default="pipeline")  # pipeline|manual

    result: Mapped[VerificationResult | None] = relationship(
        back_populates="request", uselist=False, lazy="joined", cascade="all, delete-orphan"
    )


class VerificationResult(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "verification_results"

    request_id: Mapped[str] = mapped_column(
        ForeignKey("verification_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outcome: Mapped[str] = mapped_column(
        String(24), default=VerificationOutcome.UNAVAILABLE, nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, default="")
    # [{key,label,expected,actual,passed,note}]
    checks: Mapped[list] = mapped_column(JSONB, default=list)
    raw_response: Mapped[dict] = mapped_column(JSONB, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    reference_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_source_disclaimer: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[VerificationRequest] = relationship(back_populates="result")
