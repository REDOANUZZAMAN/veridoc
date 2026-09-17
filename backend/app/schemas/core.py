from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator

from app.db.enums import ClaimStatus, DocumentType, ReviewAction
from app.schemas.common import ApiModel


# --------------------------------------------------------------------- claims
class ClaimCreate(ApiModel):
    customer_name: str = Field(min_length=2, max_length=160)
    policy_number: str = Field(min_length=3, max_length=64)
    claim_type: str = Field(default="health", max_length=48)
    customer_dob: date | None = None
    customer_email: str | None = Field(default=None, max_length=255)
    customer_phone: str | None = Field(default=None, max_length=48)
    incident_date: date | None = None
    claimed_amount: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    currency: str = Field(default="USD", min_length=3, max_length=3)
    insurer: str = Field(default="Northbridge Mutual", max_length=160)
    summary: str | None = Field(default=None, max_length=4000)
    claim_number: str | None = Field(default=None, max_length=48)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class ClaimUpdate(ApiModel):
    customer_name: str | None = Field(default=None, max_length=160)
    policy_number: str | None = Field(default=None, max_length=64)
    customer_dob: date | None = None
    incident_date: date | None = None
    claimed_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    status: ClaimStatus | None = None
    summary: str | None = Field(default=None, max_length=4000)
    assigned_investigator_id: str | None = None


class ClaimDecisionRequest(ApiModel):
    decision: str = Field(pattern="^(approve|decline|refer|withdraw)$")
    reason: str = Field(min_length=12, max_length=4000)
    close_investigations: bool = True


class UserRef(ApiModel):
    id: str
    full_name: str
    email: str
    role_name: str | None = None
    initials: str | None = None


class ClaimOut(ApiModel):
    id: str
    claim_number: str
    customer_name: str
    policy_number: str
    insurer: str
    claim_type: str
    status: str
    currency: str
    claimed_amount: Decimal | None = None
    risk_score: int | None = None
    risk_band: str | None = None
    incident_date: date | None = None
    document_count: int = 0
    open_findings: int = 0
    assigned_investigator: UserRef | None = None
    created_at: datetime
    updated_at: datetime


class ClaimDetailOut(ClaimOut):
    customer_dob: date | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    summary: str | None = None
    decision: str | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    created_by: UserRef | None = None
    documents: list[dict] = []
    verification: list[dict] = []
    findings_summary: dict = {}
    investigations: list[dict] = []
    cross_document: dict = {}
    timeline: list[dict] = []


# ------------------------------------------------------------------ documents
class DocumentOut(ApiModel):
    id: str
    document_ref: str
    claim_id: str | None = None
    claim_number: str | None = None
    original_filename: str
    mime_type: str
    file_extension: str
    file_size: int
    sha256: str
    page_count: int
    source: str
    processing_status: str
    processing_message: str | None = None
    malware_status: str
    classification_type: str | None = None
    classification_label: str | None = None
    classification_confidence: float | None = None
    risk_score: int | None = None
    risk_band: str | None = None
    verification_state: str
    uploaded_at: datetime
    uploaded_by: UserRef | None = None
    finding_counts: dict = {}


class DocumentDetailOut(DocumentOut):
    artifact_prefix: str
    pages: list[dict] = []
    extracted_fields: list[dict] = []
    line_items: list[dict] = []
    ocr: list[dict] = []
    metadata_entries: list[dict] = []
    findings: list[dict] = []
    risk_assessment: dict | None = None
    latest_run: dict | None = None
    verification: list[dict] = []
    review_actions: list[dict] = []
    schema_fields: list[dict] = []
    verified_by: UserRef | None = None
    verification_note: str | None = None
    retention_expires_at: datetime | None = None


class UploadResponse(ApiModel):
    document: DocumentOut
    analysis: dict
    warnings: list[str] = []
    message: str


class AnalyzeRequest(ApiModel):
    force: bool = False
    reason: str | None = Field(default=None, max_length=500)


class ReviewRequest(ApiModel):
    action: ReviewAction
    finding_id: str | None = None
    reason: str | None = Field(default=None, max_length=2000)
    escalate_priority: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    assign_to_id: str | None = None


class ClassificationOverride(ApiModel):
    document_type: DocumentType
    reason: str = Field(min_length=8, max_length=1000)
    reanalyze: bool = True


# ---------------------------------------------------------------- verification
class VerificationRunRequest(ApiModel):
    request_types: list[str] | None = None
    overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Optional payload overrides, e.g. {'policy_number': 'POL-938472'}",
    )


# -------------------------------------------------------------- investigations
class InvestigationCreate(ApiModel):
    claim_id: str
    title: str = Field(min_length=4, max_length=200)
    document_id: str | None = None
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    assigned_to_id: str | None = None
    summary: str | None = Field(default=None, max_length=4000)


class InvestigationUpdate(ApiModel):
    status: str | None = Field(default=None,
                               pattern="^(open|in_progress|pending_information|escalated|closed)$")
    priority: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    assigned_to_id: str | None = None
    summary: str | None = Field(default=None, max_length=4000)
    resolution: str | None = Field(default=None, max_length=48)
    resolution_reason: str | None = Field(default=None, max_length=4000)


class NoteCreate(ApiModel):
    body: str = Field(min_length=3, max_length=8000)
    note_type: str = Field(default="observation", max_length=24)
    is_internal: bool = True


# ------------------------------------------------------------------- reports
class ReportCreate(ApiModel):
    document_id: str | None = None
    claim_id: str | None = None
    investigation_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)


class ReportOut(ApiModel):
    id: str
    report_ref: str
    report_type: str
    title: str
    format: str
    file_size: int
    sha256: str | None = None
    document_sha256: str | None = None
    document_id: str | None = None
    claim_id: str | None = None
    pipeline_version: str | None = None
    rules_version: str | None = None
    generated_by: UserRef | None = None
    created_at: datetime
    notes: str | None = None


# --------------------------------------------------------------------- audit
class AuditOut(ApiModel):
    id: str
    seq: int
    action: str
    resource_type: str
    resource_id: str | None = None
    summary: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    ip_address: str | None = None
    request_id: str | None = None
    before_state: Any | None = None
    after_state: Any | None = None
    metadata_json: dict = {}
    prev_hash: str | None = None
    entry_hash: str
    created_at: datetime
