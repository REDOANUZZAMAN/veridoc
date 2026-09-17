from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey
from app.db.enums import (
    DocumentSource,
    MalwareStatus,
    ProcessingStatus,
    VerificationState,
)


class Document(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_claim_status", "claim_id", "processing_status"),
        Index("ix_documents_sha256", "sha256"),
    )

    document_ref: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True
    )
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # --- immutable ingest facts -------------------------------------------------
    original_filename: Mapped[str] = mapped_column(String(320), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_prefix: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    declared_mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(32), default=DocumentSource.PORTAL_UPLOAD)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- pipeline state ---------------------------------------------------------
    processing_status: Mapped[str] = mapped_column(
        String(24), default=ProcessingStatus.UPLOADED, nullable=False, index=True
    )
    processing_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    malware_status: Mapped[str] = mapped_column(String(20), default=MalwareStatus.PENDING)
    malware_detail: Mapped[dict] = mapped_column(JSONB, default=dict)

    classification_type: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_detail: Mapped[dict] = mapped_column(JSONB, default=dict)

    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    risk_band: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    verification_state: Mapped[str] = mapped_column(
        String(32), default=VerificationState.UNVERIFIED, nullable=False, index=True
    )
    verified_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    retention_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    claim: Mapped[Claim | None] = relationship(back_populates="documents", lazy="joined")  # noqa: F821
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id], lazy="joined")
    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin",
        order_by="DocumentPage.page_number",
    )


class DocumentPage(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_pages_page"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    render_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    render_dpi: Mapped[int] = mapped_column(Integer, default=150)
    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=False)
    text_char_count: Mapped[int] = mapped_column(Integer, default=0)
    artifacts: Mapped[dict] = mapped_column(JSONB, default=dict)  # ela/noise overlay keys

    document: Mapped[Document] = relationship(back_populates="pages")


class DocumentMetadataEntry(Base, UUIDPrimaryKey, TimestampMixin):
    """Flattened, queryable metadata. ``raw`` keeps the untouched provider output."""

    __tablename__ = "document_metadata"
    __table_args__ = (Index("ix_document_metadata_doc_group", "document_id", "group_name"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_name: Mapped[str] = mapped_column(String(32), nullable=False)  # pdf_info|xmp|exif|file|structure
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_anomalous: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(400), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)


class OcrResult(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "ocr_results"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_ocr_results_page"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(48), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(40), default="unknown")
    status: Mapped[str] = mapped_column(String(20), default="completed")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    mean_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    words: Mapped[list] = mapped_column(JSONB, default=list)  # [{text,conf,bbox,line}]
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class ExtractedField(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "extracted_fields"
    __table_args__ = (Index("ix_extracted_fields_doc_key", "document_id", "field_key"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    field_label: Mapped[str] = mapped_column(String(120), nullable=False)
    value_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(24), default="string")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="ocr")
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    group_name: Mapped[str | None] = mapped_column(String(48), nullable=True)
    line_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
