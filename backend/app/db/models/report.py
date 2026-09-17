from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Report(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "reports"

    report_ref: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True
    )
    investigation_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True
    )
    generated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    report_type: Mapped[str] = mapped_column(String(32), default="document_investigation")
    format: Mapped[str] = mapped_column(String(12), default="pdf")
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(24), nullable=True)
    rules_version: Mapped[str | None] = mapped_column(String(24), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    title: Mapped[str] = mapped_column(String(200), default="Document Investigation Report")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    generated_by = relationship("User", lazy="joined")
