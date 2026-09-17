"""Cross-document analysis for a claim bundle.

Every document in a claim contributes its extracted fields. The engine compares
the same logical field across documents (with type-aware comparison: fuzzy for
names, exact-normalised for identifiers, tolerance for money, day-granularity
for dates) and also reconciles each document against the claim record itself.

A mismatch is attributed to *both* documents so it appears on either
investigation page, with the counterpart document referenced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.db.enums import FindingCategory, Severity
from app.services.extract.normalize import (
    is_same_person,
    normalize_identifier,
    normalize_name,
    parse_date,
    parse_money,
)
from app.services.forensics.base import RawFinding, clamp

DETECTOR = "cross-document-comparator"
DETECTOR_VERSION = "1.3.0"

# Pairing policies control *which document pairs* a field may be compared
# across. Two separate invoices in one claim legitimately carry different
# invoice numbers and different totals, so comparing them blindly manufactures
# findings. Policies:
#   "any"          - compare across every pair that holds the field
#   "same_party"   - only when both documents name the same person
#   "same_invoice" - only when both documents cite the same invoice reference,
#                    or one is a claim form / payment record for the other
PAIR_ANY = "any"
PAIR_SAME_PARTY = "same_party"
PAIR_SAME_INVOICE = "same_invoice"

SETTLEMENT_TYPES = {"claim_form", "receipt", "bank_payment_document"}
BILLING_TYPES = {"medical_invoice", "hospital_bill", "repair_estimate"}

# key -> {label, mode, severity, threshold, pairing}
COMPARABLE_FIELDS: dict[str, dict] = {
    "patient_name": {"label": "Patient name", "mode": "name", "severity": Severity.HIGH,
                     "threshold": 0.72, "pairing": PAIR_ANY},
    "insured_name": {"label": "Policy holder name", "mode": "name", "severity": Severity.HIGH,
                     "threshold": 0.72, "pairing": PAIR_ANY},
    "customer_name": {"label": "Customer name", "mode": "name", "severity": Severity.MEDIUM,
                      "threshold": 0.72, "pairing": PAIR_ANY},
    "date_of_birth": {"label": "Date of birth", "mode": "date", "severity": Severity.HIGH,
                      "pairing": PAIR_SAME_PARTY},
    "national_id": {"label": "National ID", "mode": "identifier", "severity": Severity.CRITICAL,
                    "pairing": PAIR_SAME_PARTY},
    "policy_number": {"label": "Policy number", "mode": "identifier", "severity": Severity.HIGH},
    "claim_number": {"label": "Claim number", "mode": "identifier", "severity": Severity.HIGH},
    "hospital_name": {"label": "Hospital / provider", "mode": "name", "severity": Severity.MEDIUM,
                      "threshold": 0.68},
    "treatment_date": {"label": "Treatment date", "mode": "date", "severity": Severity.HIGH,
                                    "pairing": PAIR_SAME_PARTY},
    "admission_date": {"label": "Admission date", "mode": "date", "severity": Severity.MEDIUM,
                                    "pairing": PAIR_SAME_PARTY},
    "discharge_date": {"label": "Discharge date", "mode": "date", "severity": Severity.MEDIUM,
                                    "pairing": PAIR_SAME_PARTY},
    "incident_date": {"label": "Incident date", "mode": "date", "severity": Severity.HIGH},

    "vehicle_registration": {"label": "Vehicle registration", "mode": "identifier",
                             "severity": Severity.HIGH},
    "vin": {"label": "VIN", "mode": "identifier", "severity": Severity.HIGH},
    "diagnosis": {"label": "Diagnosis", "mode": "name", "severity": Severity.LOW,
                  "threshold": 0.55, "pairing": PAIR_SAME_PARTY},
    "total": {"label": "Total amount", "mode": "money", "severity": Severity.HIGH,
              "pairing": PAIR_SAME_INVOICE},
    "currency": {"label": "Currency", "mode": "identifier", "severity": Severity.MEDIUM},
}

# Documents that legitimately carry a *different* total from an invoice.
TOTAL_COMPARISON_TYPES = {
    "medical_invoice", "hospital_bill", "receipt", "repair_estimate", "claim_form",
}


@dataclass(slots=True)
class DocumentSnapshot:
    document_id: str
    document_ref: str
    document_type: str
    label: str
    fields: dict[str, dict]     # key -> {value, raw, confidence, page, bbox}
    uploaded_at: str | None = None

    def value(self, key: str) -> str | None:
        entry = self.fields.get(key)
        if not entry:
            return None
        return entry.get("value") or entry.get("raw")


@dataclass(slots=True)
class CrossDocFinding:
    finding: RawFinding
    document_id: str
    counterpart_document_id: str | None
    field_key: str
    value_a: str | None
    value_b: str | None
    similarity: float | None


@dataclass(slots=True)
class CrossDocReport:
    findings: list[CrossDocFinding] = field(default_factory=list)
    comparisons: list[dict] = field(default_factory=list)
    matrix: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "documents_compared": self.matrix.get("document_count", 0),
            "fields_compared": len({c["field"] for c in self.comparisons}),
            "pairs_compared": self.matrix.get("pair_count", 0),
            "agreements": sum(1 for c in self.comparisons if c["agrees"]),
            "mismatches": sum(1 for c in self.comparisons if not c["agrees"]),
            "comparisons": self.comparisons,
            "detector": DETECTOR,
            "detector_version": DETECTOR_VERSION,
        }


def _similarity(a: str, b: str) -> float:
    from rapidfuzz import fuzz

    return fuzz.token_set_ratio(a, b) / 100.0


def _compare(mode: str, raw_a: str, raw_b: str, spec: dict) -> tuple[bool, float | None, str]:
    if mode == "name":
        na, nb = normalize_name(raw_a), normalize_name(raw_b)
        if not na or not nb:
            return True, None, "one side empty"
        score = _similarity(na, nb)
        return score >= spec.get("threshold", 0.72), score, f"token-set similarity {score:.2f}"
    if mode == "identifier":
        ia, ib = normalize_identifier(raw_a), normalize_identifier(raw_b)
        if not ia or not ib:
            return True, None, "one side empty"
        if ia == ib:
            return True, 1.0, "exact match after normalisation"
        score = _similarity(ia, ib)
        return False, score, f"normalised values differ (similarity {score:.2f})"
    if mode == "date":
        da, db = parse_date(raw_a), parse_date(raw_b)
        if not da or not db:
            return True, None, "one side unparseable"
        if da == db:
            return True, 1.0, "identical dates"
        delta = abs((da - db).days)
        return False, None, f"{delta} day(s) apart"
    if mode == "money":
        ma, _ = parse_money(raw_a)
        mb, _ = parse_money(raw_b)
        if ma is None or mb is None:
            return True, None, "one side unparseable"
        tolerance = max(Decimal("0.05"), (abs(ma) + abs(mb)) / 2 * Decimal("0.005"))
        if abs(ma - mb) <= tolerance:
            return True, 1.0, "amounts agree within tolerance"
        return False, None, f"differ by {abs(ma - mb)}"
    return raw_a.strip().lower() == raw_b.strip().lower(), None, "case-insensitive compare"


def _same_party(
    a: DocumentSnapshot, b: DocumentSnapshot, *, field_key: str | None = None
) -> bool:
    """Do the two documents concern the same individual?

    Uses the strict person comparison: a dependant shares a surname with the
    policyholder, so a subset match is not identity.
    """
    if field_key and field_key in SUBJECT_KEYS:
        subject_a, _ = _value_subject(a, field_key)
        subject_b, _ = _value_subject(b, field_key)
        return is_same_person(subject_a, subject_b)
    for key in ("patient_name", "insured_name", "customer_name"):
        if is_same_person(a.value(key), b.value(key)):
            return True
    return False


def _pair_is_comparable(
    a: DocumentSnapshot, b: DocumentSnapshot, pairing: str, field_key: str | None = None
) -> tuple[bool, str]:
    if pairing == PAIR_ANY:
        return True, ""
    if pairing == PAIR_SAME_PARTY:
        if _same_party(a, b, field_key=field_key):
            return True, ""
        return False, ("not compared - the two documents record this value for different "
                       "people, which is expected when a dependant is treated under a family "
                       "policy")
    if pairing == PAIR_SAME_INVOICE:
        ref_a = normalize_identifier(a.value("invoice_number") or "")
        ref_b = normalize_identifier(b.value("invoice_number") or "")
        if ref_a and ref_b and ref_a == ref_b:
            return True, ""
        types = {a.document_type, b.document_type}
        if types & SETTLEMENT_TYPES and types & BILLING_TYPES:
            return True, ""
        return False, ("not compared - the documents cite different invoice references, so they "
                       "record separate transactions rather than one amount stated twice")
    return True, ""


def compare_documents(
    snapshots: list[DocumentSnapshot], *, claim: dict | None = None
) -> CrossDocReport:
    report = CrossDocReport()
    report.matrix = {
        "document_count": len(snapshots),
        "pair_count": max(0, len(snapshots) * (len(snapshots) - 1) // 2),
        "documents": [{"id": s.document_id, "ref": s.document_ref, "type": s.document_type,
                       "label": s.label} for s in snapshots],
    }
    if len(snapshots) < 2 and not claim:
        return report

    for field_key, spec in COMPARABLE_FIELDS.items():
        holders = [s for s in snapshots if s.value(field_key)]
        if field_key == "total":
            holders = [s for s in holders if s.document_type in TOTAL_COMPARISON_TYPES]
        for i in range(len(holders)):
            for j in range(i + 1, len(holders)):
                a, b = holders[i], holders[j]
                comparable, skip_reason = _pair_is_comparable(
                    a, b, spec.get("pairing", PAIR_ANY), field_key
                )
                if not comparable:
                    report.comparisons.append({
                        "field": field_key, "label": spec["label"],
                        "document_a": a.document_ref, "document_b": b.document_ref,
                        "value_a": (a.value(field_key) or "")[:120],
                        "value_b": (b.value(field_key) or "")[:120],
                        "agrees": True, "similarity": None, "detail": skip_reason,
                        "mode": spec["mode"], "skipped": True,
                    })
                    continue
                raw_a, raw_b = a.value(field_key) or "", b.value(field_key) or ""
                agrees, similarity, detail = _compare(spec["mode"], raw_a, raw_b, spec)
                report.comparisons.append({
                    "field": field_key, "label": spec["label"],
                    "document_a": a.document_ref, "document_b": b.document_ref,
                    "value_a": raw_a[:120], "value_b": raw_b[:120],
                    "agrees": agrees, "similarity": similarity, "detail": detail,
                    "mode": spec["mode"],
                })
                if agrees:
                    continue
                confidence = _mismatch_confidence(a, b, field_key, similarity)
                finding = RawFinding(
                    code=f"XDOC_{field_key.upper()}_MISMATCH",
                    category=FindingCategory.CROSS_DOCUMENT, severity=spec["severity"],
                    title=f"{spec['label']} differs between {a.label} and {b.label}",
                    description=(
                        f"{spec['label']} reads “{raw_a[:80]}” on {a.label} ({a.document_ref}) "
                        f"and “{raw_b[:80]}” on {b.label} ({b.document_ref}) - {detail}. "
                        "Documents belonging to one claim should agree on this field; a "
                        "disagreement is either a transcription issue, a document belonging to a "
                        "different event, or an alteration."
                    ),
                    confidence=confidence, detector=DETECTOR, model_version=DETECTOR_VERSION,
                    page=(a.fields.get(field_key) or {}).get("page"),
                    region=(a.fields.get(field_key) or {}).get("bbox"),
                    evidence={
                        "field": field_key, "comparison_mode": spec["mode"],
                        "document_a": {"ref": a.document_ref, "type": a.document_type,
                                       "value": raw_a[:160]},
                        "document_b": {"ref": b.document_ref, "type": b.document_type,
                                       "value": raw_b[:160]},
                        "similarity": similarity, "detail": detail,
                    },
                    recommendation=("Resolve which document is authoritative before the claim "
                                    "proceeds."),
                    extras={"field_key": field_key, "value_a": raw_a[:240],
                            "value_b": raw_b[:240], "similarity": similarity},
                )
                report.findings.append(CrossDocFinding(
                    finding=finding, document_id=a.document_id,
                    counterpart_document_id=b.document_id, field_key=field_key,
                    value_a=raw_a[:240], value_b=raw_b[:240], similarity=similarity,
                ))

    if claim:
        report.findings.extend(_compare_against_claim(snapshots, claim, report))
    return report


def _mismatch_confidence(
    a: DocumentSnapshot, b: DocumentSnapshot, field_key: str, similarity: float | None
) -> float:
    conf_a = (a.fields.get(field_key) or {}).get("confidence", 0.8) or 0.8
    conf_b = (b.fields.get(field_key) or {}).get("confidence", 0.8) or 0.8
    base = min(float(conf_a), float(conf_b))
    # A near-miss on a fuzzy field is more likely to be OCR noise than an edit.
    penalty = 0.0
    if similarity is not None and similarity > 0.55:
        penalty = 0.12
    return clamp(0.55 + base * 0.4 - penalty, 0.4, 0.95)


# claim field -> (candidate document keys in priority order, comparison mode,
#                 severity, only_when_same_party)
#
# The policyholder and the patient are frequently different people (a dependant
# treated under a family policy). Comparing the claim's date of birth against a
# dependant's would manufacture a mismatch, so identity-linked fields are only
# compared when the document's party demonstrably *is* the claim customer.
CLAIM_FIELD_MAP: dict[str, tuple[tuple[str, ...], str, str, bool]] = {
    "policy_number": (("policy_number",), "identifier", Severity.HIGH, False),
    "claim_number": (("claim_number",), "identifier", Severity.MEDIUM, False),
    "customer_name": (("insured_name", "customer_name"), "name", Severity.HIGH, False),
    "customer_dob": (("date_of_birth",), "date", Severity.HIGH, True),
    "claimed_amount": (("total",), "money", Severity.HIGH, False),
    "incident_date": (("incident_date",), "date", Severity.MEDIUM, False),
}


# Whose value is it? A date of birth printed on a hospital invoice belongs to the
# patient, not to the policyholder who submitted the claim; a national ID number
# belongs to the person the identity document was issued to. Identity-linked
# comparisons must resolve the subject before comparing, or every claim made on
# behalf of a dependant reads as a mismatch.
SUBJECT_KEYS: dict[str, tuple[str, ...]] = {
    "date_of_birth": ("patient_name", "insured_name", "customer_name"),
    "national_id": ("customer_name", "insured_name", "patient_name"),
}


def _value_subject(snap: DocumentSnapshot, doc_key: str) -> tuple[str | None, str | None]:
    """Returns (subject_name, source_field) for an identity-linked value."""
    for key in SUBJECT_KEYS.get(doc_key, ()):
        value = snap.value(key)
        if value:
            return value, key
    return None, None


def _subject_is_claim_customer(
    snap: DocumentSnapshot, doc_key: str, claim_name: str | None
) -> tuple[bool, str]:
    if not claim_name:
        return False, "the claim record does not name a customer"
    subject, source = _value_subject(snap, doc_key)
    if subject is None:
        return False, "the document does not name the person this value belongs to"
    if is_same_person(subject, claim_name):
        return True, ""
    return False, (f"this value belongs to {subject} ({source.replace('_', ' ')}), not to the "
                   f"claim customer {claim_name}")


def _compare_against_claim(
    snapshots: list[DocumentSnapshot], claim: dict, report: CrossDocReport
) -> list[CrossDocFinding]:
    out: list[CrossDocFinding] = []
    claim_ref = claim.get("claim_number") or "claim record"
    for claim_key, (doc_keys, mode, severity, same_party_only) in CLAIM_FIELD_MAP.items():
        claim_value = claim.get(claim_key)
        if claim_value in (None, ""):
            continue
        for snap in snapshots:
            doc_key = next((k for k in doc_keys if snap.value(k)), None)
            if doc_key is None:
                continue
            spec = {"mode": mode, "threshold": 0.72, "severity": severity,
                    "label": doc_key.replace("_", " ").title()}
            doc_value = snap.value(doc_key)
            if doc_key == "total" and snap.document_type not in TOTAL_COMPARISON_TYPES:
                continue
            if same_party_only:
                same, reason = _subject_is_claim_customer(
                    snap, doc_key, claim.get("customer_name")
                )
                if not same:
                    report.comparisons.append({
                        "field": doc_key, "label": spec["label"], "document_a": claim_ref,
                        "document_b": snap.document_ref, "value_a": str(claim_value)[:120],
                        "value_b": str(doc_value)[:120], "agrees": True, "similarity": None,
                        "detail": f"not compared - {reason}",
                        "mode": mode, "against_claim_record": True, "skipped": True,
                    })
                    continue
            agrees, similarity, detail = _compare(mode, str(claim_value), str(doc_value), spec)
            report.comparisons.append({
                "field": doc_key, "label": spec["label"], "document_a": claim_ref,
                "document_b": snap.document_ref, "value_a": str(claim_value)[:120],
                "value_b": str(doc_value)[:120], "agrees": agrees, "similarity": similarity,
                "detail": detail, "mode": mode, "against_claim_record": True,
            })
            if agrees:
                continue
            finding = RawFinding(
                code=f"XDOC_CLAIM_{doc_key.upper()}_MISMATCH",
                category=FindingCategory.CROSS_DOCUMENT, severity=severity,
                title=f"{spec['label']} on {snap.label} differs from the claim record",
                description=(
                    f"The claim record {claim_ref} states {spec['label'].lower()} "
                    f"“{str(claim_value)[:80]}”, while {snap.label} ({snap.document_ref}) shows "
                    f"“{str(doc_value)[:80]}” - {detail}. Supporting documents are expected to "
                    "corroborate the submitted claim particulars."
                ),
                confidence=clamp(
                    0.6 + float((snap.fields.get(doc_key) or {}).get("confidence", 0.8)) * 0.3,
                    0.5, 0.95),
                detector=DETECTOR, model_version=DETECTOR_VERSION,
                page=(snap.fields.get(doc_key) or {}).get("page"),
                region=(snap.fields.get(doc_key) or {}).get("bbox"),
                evidence={"field": doc_key, "claim_value": str(claim_value)[:160],
                          "document_value": str(doc_value)[:160], "detail": detail,
                          "comparison_mode": mode, "source": "claim_record"},
                recommendation="Reconcile the claim particulars with the submitted evidence.",
                extras={"field_key": doc_key, "value_a": str(claim_value)[:240],
                        "value_b": str(doc_value)[:240], "similarity": similarity},
            )
            out.append(CrossDocFinding(
                finding=finding, document_id=snap.document_id, counterpart_document_id=None,
                field_key=doc_key, value_a=str(claim_value)[:240], value_b=str(doc_value)[:240],
                similarity=similarity,
            ))
    return out
