from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.enums import InvestigationStatus


class Investigation(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "investigations"

    case_number: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=InvestigationStatus.OPEN, nullable=False, index=True
    )
    priority: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    assigned_to_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opened_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(48), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_score_at_open: Mapped[int | None] = mapped_column(nullable=True)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)

    assigned_to = relationship("User", foreign_keys=[assigned_to_id], lazy="joined")
    opened_by = relationship("User", foreign_keys=[opened_by_id], lazy="joined")
    notes: Mapped[list[InvestigationNote]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", lazy="selectin",
        order_by="InvestigationNote.created_at",
    )


class InvestigationNote(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "investigation_notes"

    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(String(24), default="observation")
    is_internal: Mapped[bool] = mapped_column(Boolean, default=True)
    attachments: Mapped[list] = mapped_column(JSONB, default=list)

    investigation: Mapped[Investigation] = relationship(back_populates="notes")
    author = relationship("User", lazy="joined")


class ReviewActionRecord(Base, UUIDPrimaryKey, TimestampMixin):
    """Human decisions on machine findings. Append-only by convention."""

    __tablename__ = "review_actions"

    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True
    )
    investigation_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True
    )
    finding_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finding_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(48), nullable=True)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)

    actor = relationship("User", lazy="joined")
