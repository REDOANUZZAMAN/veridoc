"""Canonical string enums shared by the API, the workers and the frontend."""
from __future__ import annotations

from enum import StrEnum


class ProcessingStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    PARTIAL = "partial"          # completed, but >=1 stage degraded
    FAILED = "failed"
    QUARANTINED = "quarantined"  # security check rejected the payload


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class DocumentType(StrEnum):
    MEDICAL_INVOICE = "medical_invoice"
    HOSPITAL_BILL = "hospital_bill"
    PRESCRIPTION = "prescription"
    IDENTITY_DOCUMENT = "identity_document"
    INSURANCE_CERTIFICATE = "insurance_certificate"
    CLAIM_FORM = "claim_form"
    VEHICLE_DOCUMENT = "vehicle_document"
    REPAIR_ESTIMATE = "repair_estimate"
    RECEIPT = "receipt"
    POLICE_REPORT = "police_report"
    BANK_PAYMENT_DOCUMENT = "bank_payment_document"
    OTHER = "other"


DOCUMENT_TYPE_LABELS: dict[str, str] = {
    DocumentType.MEDICAL_INVOICE: "Medical Invoice",
    DocumentType.HOSPITAL_BILL: "Hospital Bill",
    DocumentType.PRESCRIPTION: "Prescription",
    DocumentType.IDENTITY_DOCUMENT: "Identity Document",
    DocumentType.INSURANCE_CERTIFICATE: "Insurance Certificate",
    DocumentType.CLAIM_FORM: "Claim Form",
    DocumentType.VEHICLE_DOCUMENT: "Vehicle Document",
    DocumentType.REPAIR_ESTIMATE: "Repair Estimate",
    DocumentType.RECEIPT: "Receipt",
    DocumentType.POLICE_REPORT: "Police Report",
    DocumentType.BANK_PAYMENT_DOCUMENT: "Bank / Payment Document",
    DocumentType.OTHER: "Other",
}


class VerificationState(StrEnum):
    """Human-owned verdict for a document. Machine analysis never writes this."""

    UNVERIFIED = "unverified"
    IN_REVIEW = "in_review"
    VERIFIED = "verified"
    INFORMATION_REQUESTED = "information_requested"
    REJECTED = "rejected"


class RiskBand(StrEnum):
    LOW_CONCERN = "low_concern"
    REVIEW_RECOMMENDED = "review_recommended"
    HIGH_CONCERN = "high_concern"


RISK_BAND_LABELS = {
    RiskBand.LOW_CONCERN: "Low Concern",
    RiskBand.REVIEW_RECOMMENDED: "Review Recommended",
    RiskBand.HIGH_CONCERN: "High Concern",
}


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class FindingCategory(StrEnum):
    METADATA = "metadata"
    FORENSICS = "forensics"
    AIGC = "aigc"
    TAMPERING = "tampering"
    CONSISTENCY = "consistency"
    CROSS_DOCUMENT = "cross_document"
    VERIFICATION = "verification"
    SECURITY = "security"


class FindingStatus(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    INFORMATION_REQUESTED = "information_requested"


class ClaimStatus(StrEnum):
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    VERIFIED = "verified"
    REVIEW_REQUIRED = "review_required"
    INVESTIGATION = "investigation"
    RESOLVED = "resolved"


class InvestigationStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING_INFORMATION = "pending_information"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ReviewAction(StrEnum):
    CONFIRM_FINDING = "confirm_finding"
    DISMISS_FINDING = "dismiss_finding"
    REQUEST_INFORMATION = "request_information"
    MARK_DOCUMENT_VERIFIED = "mark_document_verified"
    REJECT_DOCUMENT = "reject_document"
    ESCALATE_INVESTIGATION = "escalate_investigation"


REVIEW_ACTIONS_REQUIRING_REASON = {
    ReviewAction.CONFIRM_FINDING,
    ReviewAction.DISMISS_FINDING,
    ReviewAction.REJECT_DOCUMENT,
    ReviewAction.ESCALATE_INVESTIGATION,
    ReviewAction.MARK_DOCUMENT_VERIFIED,
}


class VerificationOutcome(StrEnum):
    MATCH = "match"
    PARTIAL_MATCH = "partial_match"
    MISMATCH = "mismatch"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"


class MalwareStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    INFECTED = "infected"
    UNAVAILABLE = "unavailable"


class DocumentSource(StrEnum):
    PORTAL_UPLOAD = "portal_upload"
    AGENT_UPLOAD = "agent_upload"
    EMAIL_INTAKE = "email_intake"
    PARTNER_API = "partner_api"
    SEED_DEMO = "seed_demo"


class ProviderKind(StrEnum):
    OCR = "ocr"
    AIGC = "aigc"
    VERIFICATION = "verification"
    STORAGE = "storage"
    MALWARE = "malware"


class AuditAction(StrEnum):
    USER_LOGIN = "user.login"
    USER_LOGIN_FAILED = "user.login_failed"
    USER_LOGOUT = "user.logout"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_VIEWED = "document.viewed"
    DOCUMENT_DOWNLOADED = "document.downloaded"
    DOCUMENT_DELETED = "document.deleted"
    ANALYSIS_STARTED = "analysis.started"
    ANALYSIS_COMPLETED = "analysis.completed"
    ANALYSIS_FAILED = "analysis.failed"
    FINDING_CREATED = "finding.created"
    FINDING_MODIFIED = "finding.modified"
    REVIEW_ACTION = "review.action"
    REPORT_GENERATED = "report.generated"
    CLAIM_CREATED = "claim.created"
    CLAIM_STATUS_CHANGED = "claim.status_changed"
    CLAIM_DECISION = "claim.decision"
    VERIFICATION_REQUESTED = "verification.requested"
    VERIFICATION_COMPLETED = "verification.completed"
    INVESTIGATION_CREATED = "investigation.created"
    INVESTIGATION_UPDATED = "investigation.updated"
    INVESTIGATION_NOTE_ADDED = "investigation.note_added"
    RULE_UPDATED = "rule.updated"
    PROVIDER_UPDATED = "provider.updated"
    SETTING_UPDATED = "setting.updated"
