from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.enums import ProcessingStatus


class AnalysisRun(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "analysis_runs"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True
    )
    triggered_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default=ProcessingStatus.QUEUED, index=True)
    queue_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    queue_mode: Mapped[str] = mapped_column(String(16), default="redis")
    pipeline_version: Mapped[str] = mapped_column(String(24), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(24), nullable=False)
    # [{key,label,status,started_at,finished_at,duration_ms,message,findings,provider}]
    stages: Mapped[list] = mapped_column(JSONB, default=list)
    provider_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    reprocess_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )


class RiskAssessment(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "risk_assessments"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    band: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    weights_version: Mapped[str] = mapped_column(String(24), nullable=False)
    # [{code,label,category,severity,confidence,weight,contribution,evidence_ref,source}]
    signals: Mapped[list] = mapped_column(JSONB, default=list)
    category_scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    top_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    interpretation_note: Mapped[str] = mapped_column(Text, default="")
    coverage: Mapped[dict] = mapped_column(JSONB, default=dict)  # which stages contributed
    is_superseded: Mapped[bool] = mapped_column(default=False)

    run: Mapped[AnalysisRun | None] = relationship(lazy="noload")
