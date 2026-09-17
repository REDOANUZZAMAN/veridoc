from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class AuditLog(Base, UUIDPrimaryKey, TimestampMixin):
    """Append-only audit trail with a tamper-evident hash chain.

    ``entry_hash = sha256(prev_hash || canonical(entry))``. Nothing in the API
    updates or deletes a row here; ``/api/audit-logs/chain/verify`` recomputes
    the chain so a reviewer can demonstrate the log was not rewritten.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    # A gap-free, monotonically increasing ordinal: the chain is verified in this
    # order, so it must be assigned by the database rather than by the client.
    seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), unique=True, nullable=False, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(48), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(48), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(320), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    actor = relationship("User", lazy="joined")
