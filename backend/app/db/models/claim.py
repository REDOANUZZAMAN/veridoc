from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey
from app.db.enums import ClaimStatus


class Claim(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "claims"

    claim_number: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(48), nullable=True)
    policy_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    insurer: Mapped[str] = mapped_column(String(160), default="Northbridge Mutual")
    claim_type: Mapped[str] = mapped_column(String(48), default="health")
    incident_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(
        String(32), default=ClaimStatus.SUBMITTED, nullable=False, index=True
    )
    risk_score: Mapped[int | None] = mapped_column(nullable=True, index=True)
    risk_band: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(48), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_investigator_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    context: Mapped[dict] = mapped_column(JSONB, default=dict)

    documents: Mapped[list[Document]] = relationship(  # noqa: F821
        back_populates="claim", lazy="selectin"
    )
    assigned_investigator = relationship("User", foreign_keys=[assigned_investigator_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
