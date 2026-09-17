"""Trusted-source verification abstraction.

Verification is the only signal in this platform that can *confirm* something,
as opposed to flagging an anomaly - which is exactly why its provenance must be
unambiguous. Every result therefore carries:

* ``provider_mode``     - ``demo`` or ``production``
* ``is_demo_data``      - true when the answer came from the bundled sample registry
* ``data_source_disclaimer`` - printed next to the result in the UI and the report

Nothing in the codebase can present demo data as a real external confirmation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.db.enums import VerificationOutcome

DEMO_DISCLAIMER = (
    "DEMO VERIFICATION PROVIDER - this answer came from a bundled sample registry shipped with "
    "the platform for demonstration and testing. No external insurer, hospital, government or "
    "banking system was contacted. Do not treat it as a real-world confirmation."
)


@dataclass(slots=True)
class VerificationCheck:
    key: str
    label: str
    expected: str | None
    actual: str | None
    passed: bool | None            # None = could not be evaluated
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "expected": self.expected,
            "actual": self.actual, "passed": self.passed, "note": self.note,
        }


@dataclass(slots=True)
class VerificationQuery:
    request_type: str
    payload: dict
    document_id: str | None = None
    claim_id: str | None = None


@dataclass(slots=True)
class VerificationResponse:
    outcome: str
    summary: str
    checks: list[VerificationCheck] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    latency_ms: int = 0
    reference_id: str | None = None
    is_demo_data: bool = True
    disclaimer: str = DEMO_DISCLAIMER
    error: str | None = None

    @property
    def failed_checks(self) -> list[VerificationCheck]:
        return [c for c in self.checks if c.passed is False]

    def as_dict(self) -> dict:
        return {
            "outcome": self.outcome, "summary": self.summary,
            "checks": [c.as_dict() for c in self.checks], "latency_ms": self.latency_ms,
            "reference_id": self.reference_id, "is_demo_data": self.is_demo_data,
            "disclaimer": self.disclaimer, "error": self.error, "raw": self.raw,
        }


class VerificationProvider(ABC):
    key: str = "abstract"
    label: str = "Abstract verification provider"
    mode: str = "demo"
    request_types: tuple[str, ...] = ()
    description: str = ""

    def available(self) -> tuple[bool, str]:
        return True, "ready"

    @abstractmethod
    def verify(self, query: VerificationQuery) -> VerificationResponse: ...

    def describe(self) -> dict:
        ok, detail = self.available()
        return {
            "key": self.key, "label": self.label, "mode": self.mode,
            "request_types": list(self.request_types), "description": self.description,
            "available": ok, "detail": detail,
            "is_demo": self.mode == "demo",
        }


# Failing one of these means the source *contradicts* the document, rather than
# merely disagreeing on a detail: the record exists but does not support the
# claim. Those outcomes are reported as a mismatch.
CRITICAL_CHECK_KEYS = {
    "policy_active", "date_in_cover", "provider_accredited", "document_valid",
    "payment_settled", "no_write_off_marker", "registration_status", "amount_match",
    "holder_match", "customer_match", "keeper_match", "vin_match",
}


def outcome_from_checks(checks: list[VerificationCheck], *, found: bool) -> str:
    if not found:
        return VerificationOutcome.NOT_FOUND
    evaluated = [c for c in checks if c.passed is not None]
    if not evaluated:
        return VerificationOutcome.PARTIAL_MATCH
    failed = [c for c in evaluated if not c.passed]
    if not failed:
        return VerificationOutcome.MATCH
    if any(c.key in CRITICAL_CHECK_KEYS for c in failed):
        return VerificationOutcome.MISMATCH
    if len(failed) == len(evaluated):
        return VerificationOutcome.MISMATCH
    return VerificationOutcome.PARTIAL_MATCH
