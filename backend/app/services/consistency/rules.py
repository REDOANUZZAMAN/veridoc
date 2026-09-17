"""Internal-consistency rule catalogue.

Each rule is a small, independently testable function over a
:class:`RuleContext`. Rules declare their own metadata (code, severity, weight,
tunable params) which the admin panel can override per install - the engine
reads the effective configuration at run time, so thresholds are data.

Rules return ``None`` when they do not apply (missing inputs), a finding when
they fail, and an empty list when they pass. The engine records all three
outcomes so the UI can show what was checked *and passed*, not only failures.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.core.config import RULES_VERSION
from app.db.enums import FindingCategory, Severity
from app.services.extract.engine import FieldValue, LineItem
from app.services.extract.normalize import (
    parse_date,
    parse_money,
    person_similarity,
)
from app.services.forensics.base import RawFinding

DETECTOR = "consistency-rule-engine"

MONEY_TOLERANCE_ABS = Decimal("0.05")
MONEY_TOLERANCE_REL = Decimal("0.005")


@dataclass(slots=True)
class RuleContext:
    document_type: str
    fields: dict[str, FieldValue]
    line_items: list[LineItem]
    page_texts: dict[int, str] = field(default_factory=dict)
    required_keys: list[str] = field(default_factory=list)
    today: date = field(default_factory=date.today)
    currency: str | None = None

    def money(self, key: str) -> Decimal | None:
        f = self.fields.get(key)
        if not f:
            return None
        amount, _ = parse_money(f.value_normalized or f.value_raw)
        return amount

    def date(self, key: str) -> date | None:
        f = self.fields.get(key)
        if not f:
            return None
        return parse_date(f.value_normalized or f.value_raw)

    def text(self, key: str) -> str | None:
        f = self.fields.get(key)
        if not f:
            return None
        return (f.value_normalized or f.value_raw or "").strip() or None

    def page_of(self, key: str) -> int | None:
        f = self.fields.get(key)
        return f.page if f else None

    def bbox_of(self, key: str) -> dict | None:
        f = self.fields.get(key)
        return f.bbox if f else None

    def all_text(self) -> str:
        return "\n".join(self.page_texts.values())


@dataclass(slots=True)
class RuleDefinition:
    code: str
    name: str
    description: str
    default_severity: str
    weight: float
    fn: Callable[[RuleContext, dict], list[RawFinding] | None]
    applies_to: tuple[str, ...] = ()          # empty = every document type
    params: dict = field(default_factory=dict)
    version: str = "1.0.0"


REGISTRY: list[RuleDefinition] = []


def rule(
    code: str, name: str, description: str, severity: str, weight: float,
    applies_to: tuple[str, ...] = (), params: dict | None = None, version: str = "1.0.0",
):
    def wrap(fn):
        REGISTRY.append(RuleDefinition(
            code=code, name=name, description=description, default_severity=severity,
            weight=weight, fn=fn, applies_to=applies_to, params=params or {}, version=version,
        ))
        return fn

    return wrap


def _finding(
    code: str, cfg: dict, *, title: str, description: str, confidence: float,
    page: int | None = None, region: dict | None = None, expected=None, actual=None,
    fields_involved: list[str] | None = None, evidence: dict | None = None,
    recommendation: str | None = None,
) -> RawFinding:
    return RawFinding(
        code=code, category=FindingCategory.CONSISTENCY,
        severity=cfg.get("severity", Severity.MEDIUM), title=title, description=description,
        confidence=confidence, detector=DETECTOR, model_version=RULES_VERSION, page=page,
        region=region, evidence=evidence or {}, recommendation=recommendation,
        extras={
            "rule_code": code,
            "fields_involved": fields_involved or [],
            "expected": None if expected is None else str(expected)[:240],
            "actual": None if actual is None else str(actual)[:240],
            "rule_version": cfg.get("version", RULES_VERSION),
        },
    )


def _close(a: Decimal, b: Decimal) -> bool:
    tolerance = max(MONEY_TOLERANCE_ABS, (abs(a) + abs(b)) / 2 * MONEY_TOLERANCE_REL)
    return abs(a - b) <= tolerance


# --------------------------------------------------------------------------- #
# Arithmetic rules
# --------------------------------------------------------------------------- #
@rule("LINE_ITEM_SUM_MISMATCH", "Line items must sum to the stated subtotal or total",
      "Adds every extracted line-item amount and compares it against the subtotal (or the total "
      "when no subtotal is printed).", Severity.HIGH, 18.0,
      params={"min_items": 2})
def line_item_sum(ctx: RuleContext, cfg: dict):
    items = [i for i in ctx.line_items if i.amount is not None]
    if len(items) < int(cfg.get("params", {}).get("min_items", 2)):
        return None
    subtotal = ctx.money("subtotal")
    total = ctx.money("total")
    target_key = "subtotal" if subtotal is not None else "total"
    target = subtotal if subtotal is not None else total
    if target is None:
        return None
    computed = sum((i.amount for i in items), Decimal("0"))
    if _close(computed, target):
        return []
    # If a tax line explains the gap exactly, the subtotal is fine.
    tax = ctx.money("tax") or Decimal("0")
    if target_key == "total" and _close(computed + tax, target):
        return []
    difference = target - computed
    return [_finding(
        "LINE_ITEM_SUM_MISMATCH", cfg,
        title=f"Line items do not sum to the stated {target_key.replace('_', ' ')}",
        description=(
            f"The {len(items)} extracted line items add up to {computed}, but the document "
            f"states a {target_key.replace('_', ' ')} of {target} - a difference of "
            f"{difference}. Either a line was altered, a line is missing from the extraction, "
            "or an undisclosed adjustment was applied."
        ),
        confidence=0.9 if abs(difference) > Decimal("1") else 0.6,
        page=ctx.page_of(target_key), region=ctx.bbox_of(target_key),
        expected=computed, actual=target,
        fields_involved=["line_items", target_key],
        evidence={"line_item_count": len(items), "computed_sum": str(computed),
                  "stated_value": str(target), "difference": str(difference),
                  "items": [i.as_dict() for i in items[:20]]},
        recommendation="Request an itemised statement from the issuer and reconcile line by line.",
    )]


@rule("TOTAL_ARITHMETIC_MISMATCH", "Subtotal - discount + tax must equal the total",
      "Recomputes the document total from its own printed components.",
      Severity.HIGH, 18.0)
def total_arithmetic(ctx: RuleContext, cfg: dict):
    subtotal, tax, total = ctx.money("subtotal"), ctx.money("tax"), ctx.money("total")
    discount = ctx.money("discount") or Decimal("0")
    if subtotal is None or total is None:
        return None
    computed = subtotal - discount + (tax or Decimal("0"))
    if _close(computed, total):
        return []
    return [_finding(
        "TOTAL_ARITHMETIC_MISMATCH", cfg,
        title="Printed total does not match its own components",
        description=(
            f"Subtotal {subtotal} minus discount {discount} plus tax {tax or 0} gives "
            f"{computed}, but the document states {total}. An edited total is the most common "
            "cause; so is a component the extractor could not read."
        ),
        confidence=0.88, page=ctx.page_of("total"), region=ctx.bbox_of("total"),
        expected=computed, actual=total,
        fields_involved=["subtotal", "discount", "tax", "total"],
        evidence={"subtotal": str(subtotal), "discount": str(discount),
                  "tax": str(tax) if tax is not None else None, "computed_total": str(computed),
                  "stated_total": str(total), "difference": str(total - computed)},
        recommendation="Confirm the payable amount with the issuer before settlement.",
    )]


@rule("TAX_CALCULATION_MISMATCH", "Tax must equal subtotal x tax rate",
      "Checks the printed tax amount against the printed tax rate.",
      Severity.MEDIUM, 10.0, params={"tolerance_pct": 1.5})
def tax_calculation(ctx: RuleContext, cfg: dict):
    subtotal, tax = ctx.money("subtotal"), ctx.money("tax")
    rate_field = ctx.fields.get("tax_rate")
    if subtotal is None or tax is None or rate_field is None:
        return None
    rate, _ = parse_money(rate_field.value_normalized or rate_field.value_raw)
    if rate is None or rate <= 0:
        return None
    expected = (subtotal * rate / Decimal("100")).quantize(Decimal("0.01"))
    tolerance = max(Decimal("0.05"), expected * Decimal(str(cfg.get("params", {})
                                                           .get("tolerance_pct", 1.5))) / 100)
    if abs(expected - tax) <= tolerance:
        return []
    implied = (tax / subtotal * 100).quantize(Decimal("0.01")) if subtotal else None
    return [_finding(
        "TAX_CALCULATION_MISMATCH", cfg,
        title=f"Tax amount inconsistent with the stated {rate}% rate",
        description=(f"At {rate}% of {subtotal} the tax should be {expected}, but {tax} is "
                     f"printed (an implied rate of {implied}%)."),
        confidence=0.78, page=ctx.page_of("tax"), region=ctx.bbox_of("tax"),
        expected=expected, actual=tax, fields_involved=["subtotal", "tax", "tax_rate"],
        evidence={"subtotal": str(subtotal), "stated_tax": str(tax),
                  "stated_rate_pct": str(rate), "expected_tax": str(expected),
                  "implied_rate_pct": str(implied)},
    )]


@rule("BALANCE_MISMATCH", "Total minus amount paid must equal the balance due",
      "Reconciles the payment block of the document.", Severity.MEDIUM, 9.0)
def balance_mismatch(ctx: RuleContext, cfg: dict):
    total, paid, balance = ctx.money("total"), ctx.money("amount_paid"), ctx.money("balance_due")
    if total is None or paid is None or balance is None:
        return None
    computed = total - paid
    if _close(computed, balance):
        return []
    return [_finding(
        "BALANCE_MISMATCH", cfg, title="Payment block does not reconcile",
        description=(f"Total {total} less amount paid {paid} gives {computed}, but the balance "
                     f"due is printed as {balance}."),
        confidence=0.76, page=ctx.page_of("balance_due"), region=ctx.bbox_of("balance_due"),
        expected=computed, actual=balance,
        fields_involved=["total", "amount_paid", "balance_due"],
        evidence={"total": str(total), "amount_paid": str(paid), "balance_due": str(balance)},
    )]


@rule("AMOUNT_PAID_EXCEEDS_TOTAL", "Amount paid cannot exceed the total",
      "Flags a payment larger than the amount billed.", Severity.MEDIUM, 10.0)
def paid_exceeds_total(ctx: RuleContext, cfg: dict):
    total, paid = ctx.money("total"), ctx.money("amount_paid")
    if total is None or paid is None:
        return None
    if paid <= total + MONEY_TOLERANCE_ABS:
        return []
    return [_finding(
        "AMOUNT_PAID_EXCEEDS_TOTAL", cfg, title="Amount paid exceeds the document total",
        description=f"The document records a payment of {paid} against a total of {total}.",
        confidence=0.8, page=ctx.page_of("amount_paid"), region=ctx.bbox_of("amount_paid"),
        expected=f"<= {total}", actual=paid, fields_involved=["total", "amount_paid"],
        evidence={"total": str(total), "amount_paid": str(paid),
                  "excess": str(paid - total)},
    )]


@rule("NON_POSITIVE_TOTAL", "Total must be a positive amount",
      "Catches zero, blank or negative totals on a billing document.",
      Severity.MEDIUM, 8.0,
      applies_to=("medical_invoice", "hospital_bill", "repair_estimate", "receipt"))
def non_positive_total(ctx: RuleContext, cfg: dict):
    total = ctx.money("total")
    if total is None:
        return None
    if total > 0:
        return []
    return [_finding(
        "NON_POSITIVE_TOTAL", cfg, title="Document total is not a positive amount",
        description=f"The extracted total is {total}, which cannot be settled as billed.",
        confidence=0.7, page=ctx.page_of("total"), region=ctx.bbox_of("total"),
        expected="> 0", actual=total, fields_involved=["total"],
        evidence={"total": str(total)},
    )]


@rule("DUPLICATE_LINE_ITEMS", "Identical line items should not repeat",
      "Detects the same description and amount billed more than once.",
      Severity.LOW, 7.0, params={"min_repeats": 2})
def duplicate_items(ctx: RuleContext, cfg: dict):
    if len(ctx.line_items) < 2:
        return None
    seen: dict[tuple[str, str], list[LineItem]] = {}
    for item in ctx.line_items:
        key = (item.description.lower().strip(), str(item.amount))
        seen.setdefault(key, []).append(item)
    repeats = {k: v for k, v in seen.items()
               if len(v) >= int(cfg.get("params", {}).get("min_repeats", 2))}
    if not repeats:
        return []
    first = next(iter(repeats.values()))[0]
    return [_finding(
        "DUPLICATE_LINE_ITEMS", cfg, title=f"{len(repeats)} line item(s) billed more than once",
        description=("The same description and amount appears multiple times. Repeat charges are "
                     "legitimate for recurring services, and are also the simplest way to "
                     "inflate an invoice."),
        confidence=0.6, page=first.page, region=first.bbox,
        fields_involved=["line_items"],
        evidence={"duplicates": [{"description": k[0], "amount": k[1], "occurrences": len(v)}
                                 for k, v in repeats.items()][:10]},
    )]


# --------------------------------------------------------------------------- #
# Date rules
# --------------------------------------------------------------------------- #
@rule("TREATMENT_AFTER_INVOICE", "Treatment date must not be after the invoice date",
      "A service cannot be billed before it is delivered.", Severity.HIGH, 16.0,
      params={"grace_days": 0})
def treatment_after_invoice(ctx: RuleContext, cfg: dict):
    treatment, invoice = ctx.date("treatment_date"), ctx.date("invoice_date")
    if not treatment or not invoice:
        return None
    grace = int(cfg.get("params", {}).get("grace_days", 0))
    if treatment <= invoice + timedelta(days=grace):
        return []
    gap = (treatment - invoice).days
    return [_finding(
        "TREATMENT_AFTER_INVOICE", cfg, title="Treatment date falls after the invoice date",
        description=(f"Treatment is dated {treatment.isoformat()} but the invoice is dated "
                     f"{invoice.isoformat()}, {gap} day(s) earlier. Pre-billing happens for "
                     "scheduled procedures, and this ordering is also what appears when one of "
                     "the two dates has been altered."),
        confidence=0.85, page=ctx.page_of("treatment_date"), region=ctx.bbox_of("treatment_date"),
        expected=f"<= {invoice.isoformat()}", actual=treatment.isoformat(),
        fields_involved=["treatment_date", "invoice_date"],
        evidence={"treatment_date": treatment.isoformat(), "invoice_date": invoice.isoformat(),
                  "days_after": gap},
        recommendation="Confirm the service date against the provider's appointment records.",
    )]


@rule("ADMISSION_AFTER_DISCHARGE", "Admission date must precede discharge date",
      "Checks the inpatient stay window.", Severity.HIGH, 15.0)
def admission_after_discharge(ctx: RuleContext, cfg: dict):
    admission, discharge = ctx.date("admission_date"), ctx.date("discharge_date")
    if not admission or not discharge:
        return None
    if admission <= discharge:
        return []
    return [_finding(
        "ADMISSION_AFTER_DISCHARGE", cfg, title="Admission date is after the discharge date",
        description=(f"Admission {admission.isoformat()} is later than discharge "
                     f"{discharge.isoformat()}, which is not a possible stay."),
        confidence=0.9, page=ctx.page_of("admission_date"), region=ctx.bbox_of("admission_date"),
        expected=f"<= {discharge.isoformat()}", actual=admission.isoformat(),
        fields_involved=["admission_date", "discharge_date"],
        evidence={"admission_date": admission.isoformat(),
                  "discharge_date": discharge.isoformat()},
    )]


@rule("FUTURE_DATED_DOCUMENT", "Document dates must not be in the future",
      "Compares every extracted date against the processing date.", Severity.MEDIUM, 11.0,
      params={"grace_days": 1})
def future_dated(ctx: RuleContext, cfg: dict):
    grace = timedelta(days=int(cfg.get("params", {}).get("grace_days", 1)))
    out = []
    for key in ("invoice_date", "treatment_date", "prescription_date", "issue_date",
                "admission_date", "discharge_date", "incident_date"):
        value = ctx.date(key)
        if value and value > ctx.today + grace:
            out.append(_finding(
                "FUTURE_DATED_DOCUMENT", cfg,
                title=f"{key.replace('_', ' ').title()} is in the future",
                description=(f"{key.replace('_', ' ')} is {value.isoformat()}, later than the "
                             f"processing date {ctx.today.isoformat()}."),
                confidence=0.8, page=ctx.page_of(key), region=ctx.bbox_of(key),
                expected=f"<= {ctx.today.isoformat()}", actual=value.isoformat(),
                fields_involved=[key],
                evidence={key: value.isoformat(), "processed_on": ctx.today.isoformat(),
                          "days_ahead": (value - ctx.today).days},
            ))
    return out or []


@rule("IMPLAUSIBLE_DATE_OF_BIRTH", "Date of birth must give a plausible age",
      "Rejects ages below 0 or above 120 years at the document date.", Severity.MEDIUM, 9.0,
      params={"max_age": 120})
def implausible_dob(ctx: RuleContext, cfg: dict):
    dob = ctx.date("date_of_birth")
    if not dob:
        return None
    reference = ctx.date("invoice_date") or ctx.date("treatment_date") or ctx.today
    age_days = (reference - dob).days
    max_age = int(cfg.get("params", {}).get("max_age", 120))
    if 0 <= age_days <= max_age * 366:
        return []
    return [_finding(
        "IMPLAUSIBLE_DATE_OF_BIRTH", cfg, title="Date of birth is not plausible",
        description=(f"Date of birth {dob.isoformat()} against reference date "
                     f"{reference.isoformat()} gives an age of {age_days // 365} years."),
        confidence=0.72, page=ctx.page_of("date_of_birth"), region=ctx.bbox_of("date_of_birth"),
        actual=dob.isoformat(), fields_involved=["date_of_birth"],
        evidence={"date_of_birth": dob.isoformat(), "reference_date": reference.isoformat(),
                  "implied_age_years": age_days // 365},
    )]


@rule("DOCUMENT_EXPIRED_AT_EVENT", "Document must be valid at the date of the event",
      "Checks validity windows on certificates and identity documents.",
      Severity.MEDIUM, 12.0,
      applies_to=("insurance_certificate", "identity_document", "vehicle_document"))
def expired_at_event(ctx: RuleContext, cfg: dict):
    expiry = ctx.date("expiry_date") or ctx.date("valid_to")
    if not expiry:
        return None
    reference = ctx.date("incident_date") or ctx.date("treatment_date") or ctx.today
    if expiry >= reference:
        return []
    return [_finding(
        "DOCUMENT_EXPIRED_AT_EVENT", cfg,
        title="Document had expired at the relevant event date",
        description=(f"Validity ended {expiry.isoformat()}, before the reference event date "
                     f"{reference.isoformat()}."),
        confidence=0.84, page=ctx.page_of("expiry_date") or ctx.page_of("valid_to"),
        region=ctx.bbox_of("expiry_date") or ctx.bbox_of("valid_to"),
        expected=f">= {reference.isoformat()}", actual=expiry.isoformat(),
        fields_involved=["expiry_date", "valid_to"],
        evidence={"expiry_date": expiry.isoformat(), "reference_date": reference.isoformat()},
    )]


@rule("SERVICE_OUTSIDE_POLICY_WINDOW", "Service date must fall inside the cover period",
      "Compares the service date against the policy validity window printed on the document.",
      Severity.HIGH, 14.0)
def service_outside_policy(ctx: RuleContext, cfg: dict):
    start, end = ctx.date("valid_from"), ctx.date("valid_to")
    service = ctx.date("treatment_date") or ctx.date("invoice_date")
    if not service or (not start and not end):
        return None
    if (not start or service >= start) and (not end or service <= end):
        return []
    return [_finding(
        "SERVICE_OUTSIDE_POLICY_WINDOW", cfg,
        title="Service date falls outside the stated cover period",
        description=(f"Service dated {service.isoformat()} lies outside the cover window "
                     f"{start or '?'} to {end or '?'} printed on this document."),
        confidence=0.82, page=ctx.page_of("treatment_date"),
        region=ctx.bbox_of("treatment_date"),
        expected=f"{start} .. {end}", actual=service.isoformat(),
        fields_involved=["treatment_date", "valid_from", "valid_to"],
        evidence={"service_date": service.isoformat(),
                  "valid_from": start.isoformat() if start else None,
                  "valid_to": end.isoformat() if end else None},
    )]


# --------------------------------------------------------------------------- #
# Identity / format rules
# --------------------------------------------------------------------------- #
@rule("MISSING_REQUIRED_FIELD", "All required fields for the document type must be present",
      "Reports fields the schema marks as required that could not be located.",
      Severity.MEDIUM, 8.0)
def missing_required(ctx: RuleContext, cfg: dict):
    missing = [k for k in ctx.required_keys
               if k not in ctx.fields or not (ctx.fields[k].value_normalized
                                              or ctx.fields[k].value_raw)]
    if not missing:
        return []
    return [_finding(
        "MISSING_REQUIRED_FIELD", cfg,
        title=f"{len(missing)} required field(s) could not be read",
        description=("The document type schema expects these fields: "
                     f"{', '.join(missing)}. They are either absent from the document or the "
                     "extractor could not locate them - both matter, because a missing "
                     "identifier blocks verification against the issuer."),
        confidence=0.7, fields_involved=missing,
        evidence={"missing_fields": missing, "document_type": ctx.document_type},
        recommendation="Request a complete copy of the document from the claimant.",
    )]


@rule("IDENTIFIER_FORMAT_UNEXPECTED", "Reference numbers should match the expected format",
      "Compares invoice, policy and claim references against configured patterns.",
      Severity.LOW, 7.0,
      params={"patterns": {
          "invoice_number": r"^[A-Z0-9][A-Z0-9\-/]{3,23}$",
          "policy_number": r"^[A-Z]{2,4}[- ]?[A-Z0-9]{4,16}$",
          "claim_number": r"^[A-Z]{2,4}[- ]?\d{4}[- ]?\d{3,10}$",
      }})
def identifier_format(ctx: RuleContext, cfg: dict):
    patterns = cfg.get("params", {}).get("patterns", {})
    out = []
    for key, pattern in patterns.items():
        value = ctx.text(key)
        if not value:
            continue
        if re.match(pattern, value.upper()):
            continue
        out.append(_finding(
            "IDENTIFIER_FORMAT_UNEXPECTED", cfg,
            title=f"{key.replace('_', ' ').title()} does not match the expected format",
            description=(f"'{value}' does not match the configured pattern for this reference "
                         "type. Insurers and providers use stable reference formats, so a "
                         "deviation is worth checking - formats do legitimately differ between "
                         "issuers and can be reconfigured in Rules."),
            confidence=0.55, page=ctx.page_of(key), region=ctx.bbox_of(key),
            expected=pattern, actual=value, fields_involved=[key],
            evidence={"value": value, "pattern": pattern},
        ))
    return out or []


@rule("INTERNAL_NAME_MISMATCH", "Patient and policy-holder names should reconcile",
      "Compares the party names printed on the same document. Uses strict (order-sensitive) "
      "name comparison, so a dependant sharing the policyholder's surname is reported - that "
      "relationship is exactly what an assessor needs to confirm against the policy.",
      Severity.LOW, 8.0, params={"min_similarity": 0.80})
def internal_name_mismatch(ctx: RuleContext, cfg: dict):
    patient, insured = ctx.text("patient_name"), ctx.text("insured_name")
    if not patient or not insured:
        return None
    score = person_similarity(patient, insured)
    threshold = float(cfg.get("params", {}).get("min_similarity", 0.80))
    if score >= threshold:
        return []
    return [_finding(
        "INTERNAL_NAME_MISMATCH", cfg,
        title="Patient and policy-holder names differ on the same document",
        description=(f"'{patient}' and '{insured}' have a similarity of {score:.2f}. This is "
                     "entirely normal when a dependant is treated under a family policy, and it "
                     "is also what a substituted name looks like."),
        confidence=0.5, page=ctx.page_of("patient_name"), region=ctx.bbox_of("patient_name"),
        expected=insured, actual=patient, fields_involved=["patient_name", "insured_name"],
        evidence={"patient_name_similarity": round(score, 4),
                  "threshold": threshold},
        recommendation="Confirm the dependant relationship against the policy record.",
    )]


@rule("VIN_CHECK_DIGIT_INVALID", "VIN check digit must validate (ISO 3779)",
      "Recomputes the 9th-position check digit of a 17-character VIN.",
      Severity.HIGH, 14.0, applies_to=("vehicle_document", "repair_estimate"))
def vin_check_digit(ctx: RuleContext, cfg: dict):
    vin = (ctx.text("vin") or "").upper().replace(" ", "").replace("-", "")
    if len(vin) != 17 or not re.match(r"^[A-HJ-NPR-Z0-9]{17}$", vin):
        return None
    translit = {**{str(d): d for d in range(10)},
                **dict(zip("ABCDEFGH", range(1, 9), strict=True)),
                **dict(zip("JKLMNP", [1, 2, 3, 4, 5, 7], strict=True)),
                **dict(zip("RSTUVWXYZ", [9, 2, 3, 4, 5, 6, 7, 8, 9], strict=True))}
    weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(translit.get(ch, 0) * w for ch, w in zip(vin, weights, strict=True))
    remainder = total % 11
    expected = "X" if remainder == 10 else str(remainder)
    if vin[8] == expected:
        return []
    return [_finding(
        "VIN_CHECK_DIGIT_INVALID", cfg, title="VIN check digit does not validate",
        description=(f"The VIN {vin} carries check digit '{vin[8]}' but the ISO 3779 algorithm "
                     f"computes '{expected}'. A transcription error is the most common cause; a "
                     "fabricated VIN is the other."),
        confidence=0.87, page=ctx.page_of("vin"), region=ctx.bbox_of("vin"),
        expected=expected, actual=vin[8], fields_involved=["vin"],
        evidence={"vin": vin, "computed_check_digit": expected, "stated_check_digit": vin[8]},
        recommendation="Re-read the VIN from the document and verify against the vehicle registry.",
    )]


@rule("IBAN_CHECKSUM_INVALID", "IBAN must satisfy the mod-97 checksum",
      "Validates a settlement IBAN using ISO 13616.", Severity.HIGH, 13.0)
def iban_checksum(ctx: RuleContext, cfg: dict):
    raw = (ctx.text("account_number") or "").upper().replace(" ", "")
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", raw):
        return None
    rearranged = raw[4:] + raw[:4]
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        valid = int(digits) % 97 == 1
    except ValueError:
        return None
    if valid:
        return []
    return [_finding(
        "IBAN_CHECKSUM_INVALID", cfg, title="Settlement IBAN fails its checksum",
        description=(f"The account number '{raw}' is formatted as an IBAN but does not satisfy "
                     "the ISO 13616 mod-97 check, so a transfer to it would be rejected."),
        confidence=0.9, page=ctx.page_of("account_number"),
        region=ctx.bbox_of("account_number"),
        actual=raw[:8] + "...", fields_involved=["account_number"],
        evidence={"iban_prefix": raw[:8], "length": len(raw), "checksum_valid": False},
        recommendation="Obtain written confirmation of settlement details from the claimant.",
    )]


@rule("CURRENCY_AMBIGUOUS", "A document should use a single currency",
      "Detects more than one currency symbol or code across the document.",
      Severity.MEDIUM, 9.0)
def currency_ambiguous(ctx: RuleContext, cfg: dict):
    text = ctx.all_text()
    if not text:
        return None
    codes = set(re.findall(r"\b(USD|EUR|GBP|SGD|AUD|INR|BDT)\b", text))
    symbols = {s for s in ("$", "€", "£", "₹", "৳") if s in text}
    mapped = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "৳": "BDT"}
    combined = codes | {mapped[s] for s in symbols}
    if len(combined) <= 1:
        return []
    return [_finding(
        "CURRENCY_AMBIGUOUS", cfg, title=f"{len(combined)} different currencies appear",
        description=(f"The document references {', '.join(sorted(combined))}. A single "
                     "transactional document should settle in one currency; mixed currencies "
                     "make the payable amount ambiguous."),
        confidence=0.68, fields_involved=["currency", "total"],
        evidence={"currencies_detected": sorted(combined), "codes": sorted(codes),
                  "symbols": sorted(symbols)},
    )]


@rule("LOW_CONFIDENCE_CRITICAL_FIELD", "Critical fields must be read with usable confidence",
      "Flags required or monetary fields extracted below the confidence floor.",
      Severity.LOW, 6.0, params={"min_confidence": 0.62})
def low_confidence_fields(ctx: RuleContext, cfg: dict):
    floor = float(cfg.get("params", {}).get("min_confidence", 0.62))
    weak = [
        f for f in ctx.fields.values()
        if (f.required or f.value_type == "money") and f.confidence < floor
    ]
    if not weak:
        return []
    worst = min(weak, key=lambda f: f.confidence)
    return [_finding(
        "LOW_CONFIDENCE_CRITICAL_FIELD", cfg,
        title=f"{len(weak)} critical field(s) read with low confidence",
        description=("Recognition confidence is below the configured floor for fields that drive "
                     "the decision. This is a data-quality limit, not an integrity concern: "
                     "downstream checks on these values are correspondingly less reliable."),
        confidence=0.55, page=worst.page, region=worst.bbox,
        fields_involved=[f.key for f in weak],
        evidence={"floor": floor,
                  "fields": [{"key": f.key, "confidence": round(f.confidence, 3),
                              "value": (f.value_normalized or f.value_raw or "")[:60]}
                             for f in weak[:10]]},
        recommendation="Request a higher-quality scan to raise extraction confidence.",
    )]


def rules_for(document_type: str) -> list[RuleDefinition]:
    return [r for r in REGISTRY if not r.applies_to or document_type in r.applies_to]
