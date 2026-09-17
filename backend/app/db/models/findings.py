"""Detector output tables.

Five tables share :class:`FindingMixin`. They are kept apart because their
provenance differs (model-based vs rule-based vs cross-entity) and because
retention/ownership rules differ per category - but they expose one contract:

    finding_id, category, severity, confidence, page, region, description,
    evidence, detector, model_version, created_at
"""
from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, FindingMixin


class _DocumentFindingBase(FindingMixin):
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {x,y,width,height,unit}
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    recommendation: Mapped[str | None] = mapped_column(String(400), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(24), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ForensicFinding(Base, _DocumentFindingBase):
    __tablename__ = "forensic_findings"
    __table_args__ = (Index("ix_forensic_findings_doc_sev", "document_id", "severity"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    signal_group: Mapped[str] = mapped_column(String(32), default="structure")  # metadata|image|pdf


class AigcFinding(Base, _DocumentFindingBase):
    __tablename__ = "aigc_findings"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    provider_key: Mapped[str] = mapped_column(String(48), nullable=False)
    provider_label: Mapped[str] = mapped_column(String(120), nullable=False)
    is_demo_provider: Mapped[bool] = mapped_column(default=True)
    indicator_scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Probabilistic by construction: we persist the band, never a verdict.
    likelihood_band: Mapped[str] = mapped_column(String(32), default="inconclusive")


class TamperingFinding(Base, _DocumentFindingBase):
    __tablename__ = "tampering_findings"
    __table_args__ = (Index("ix_tampering_findings_doc_page", "document_id", "page"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    tamper_type: Mapped[str] = mapped_column(String(48), nullable=False)
    affected_field: Mapped[str | None] = mapped_column(String(80), nullable=True)
    affected_value: Mapped[str | None] = mapped_column(String(240), nullable=True)
    overlay_key: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ConsistencyFinding(Base, _DocumentFindingBase):
    __tablename__ = "consistency_findings"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fields_involved: Mapped[list] = mapped_column(JSONB, default=list)
    expected: Mapped[str | None] = mapped_column(String(240), nullable=True)
    actual: Mapped[str | None] = mapped_column(String(240), nullable=True)


class CrossDocumentFinding(Base, _DocumentFindingBase):
    __tablename__ = "cross_document_findings"

    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counterpart_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    value_a: Mapped[str | None] = mapped_column(String(240), nullable=True)
    value_b: Mapped[str | None] = mapped_column(String(240), nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)


FINDING_TABLES: dict[str, type] = {
    "forensic": ForensicFinding,
    "aigc": AigcFinding,
    "tampering": TamperingFinding,
    "consistency": ConsistencyFinding,
    "cross_document": CrossDocumentFinding,
}
