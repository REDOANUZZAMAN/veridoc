"""Role based access control.

Authorisation is enforced server side only - the frontend uses the same matrix
to hide controls, but every mutating endpoint re-checks here.
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    FRAUD_INVESTIGATOR = "fraud_investigator"
    CLAIMS_OFFICER = "claims_officer"
    REVIEWER = "reviewer"


ROLE_LABELS: dict[str, str] = {
    Role.ADMIN: "Administrator",
    Role.FRAUD_INVESTIGATOR: "Fraud Investigator",
    Role.CLAIMS_OFFICER: "Claims Officer",
    Role.REVIEWER: "Reviewer",
}


class Perm(StrEnum):
    DASHBOARD_READ = "dashboard:read"

    DOCUMENT_READ = "document:read"
    DOCUMENT_UPLOAD = "document:upload"
    DOCUMENT_DOWNLOAD = "document:download"
    DOCUMENT_ANALYZE = "document:analyze"
    DOCUMENT_VERIFY = "document:verify"
    DOCUMENT_DELETE = "document:delete"

    CLAIM_READ = "claim:read"
    CLAIM_CREATE = "claim:create"
    CLAIM_UPDATE = "claim:update"
    CLAIM_DECIDE = "claim:decide"

    FINDING_CONFIRM = "finding:confirm"
    FINDING_DISMISS = "finding:dismiss"
    FINDING_REQUEST_INFO = "finding:request_info"

    INVESTIGATION_READ = "investigation:read"
    INVESTIGATION_ASSIGN = "investigation:assign"
    INVESTIGATION_NOTE = "investigation:note"
    INVESTIGATION_ESCALATE = "investigation:escalate"
    INVESTIGATION_CLOSE = "investigation:close"

    VERIFICATION_RUN = "verification:run"
    VERIFICATION_READ = "verification:read"

    REPORT_READ = "report:read"
    REPORT_GENERATE = "report:generate"

    AUDIT_READ = "audit:read"

    RULE_READ = "rule:read"
    RULE_WRITE = "rule:write"

    PROVIDER_READ = "provider:read"
    PROVIDER_WRITE = "provider:write"

    USER_READ = "user:read"
    USER_WRITE = "user:write"

    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"


_READ_ONLY_CORE = {
    Perm.DASHBOARD_READ, Perm.DOCUMENT_READ, Perm.DOCUMENT_DOWNLOAD, Perm.CLAIM_READ,
    Perm.INVESTIGATION_READ, Perm.VERIFICATION_READ, Perm.REPORT_READ, Perm.RULE_READ,
    Perm.PROVIDER_READ, Perm.SETTINGS_READ,
}

ROLE_PERMISSIONS: dict[str, set[Perm]] = {
    Role.ADMIN: set(Perm),
    Role.FRAUD_INVESTIGATOR: _READ_ONLY_CORE
    | {
        Perm.DOCUMENT_UPLOAD, Perm.DOCUMENT_ANALYZE, Perm.DOCUMENT_VERIFY,
        Perm.CLAIM_UPDATE,
        Perm.FINDING_CONFIRM, Perm.FINDING_DISMISS, Perm.FINDING_REQUEST_INFO,
        Perm.INVESTIGATION_ASSIGN, Perm.INVESTIGATION_NOTE, Perm.INVESTIGATION_ESCALATE,
        Perm.INVESTIGATION_CLOSE,
        Perm.VERIFICATION_RUN, Perm.REPORT_GENERATE, Perm.AUDIT_READ,
    },
    Role.CLAIMS_OFFICER: _READ_ONLY_CORE
    | {
        Perm.DOCUMENT_UPLOAD, Perm.DOCUMENT_ANALYZE,
        Perm.CLAIM_CREATE, Perm.CLAIM_UPDATE, Perm.CLAIM_DECIDE,
        Perm.FINDING_REQUEST_INFO, Perm.INVESTIGATION_NOTE, Perm.INVESTIGATION_ESCALATE,
        Perm.VERIFICATION_RUN, Perm.REPORT_GENERATE,
    },
    # A reviewer performs second-line review of machine findings but cannot
    # escalate, decide a claim, or run external verification.
    Role.REVIEWER: _READ_ONLY_CORE
    | {
        Perm.FINDING_CONFIRM, Perm.FINDING_DISMISS, Perm.FINDING_REQUEST_INFO,
        Perm.INVESTIGATION_NOTE, Perm.DOCUMENT_ANALYZE,
    },
}

ROLE_DESCRIPTIONS = {
    Role.ADMIN: "Full platform control: users, rules, providers, thresholds, audit.",
    Role.FRAUD_INVESTIGATOR: "Owns investigations: reviews findings, escalates, runs verification, issues reports.",
    Role.CLAIMS_OFFICER: "Creates claims, uploads documents, requests information and records the final claim decision.",
    Role.REVIEWER: "Second-line reviewer: confirms or dismisses machine findings with a documented reason.",
}


def permissions_for(role: str) -> set[Perm]:
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: str, perm: Perm) -> bool:
    return perm in permissions_for(role)
