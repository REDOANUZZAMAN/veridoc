"""Lexical + structural signatures per document type.

Each entry is a weighted term list. Terms are matched as word-boundary regexes
against the normalised page text, so the classifier is explainable: every score
can be traced to the exact terms that fired.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db.enums import DocumentType


@dataclass(slots=True)
class TypeSignature:
    document_type: str
    strong: tuple[str, ...] = ()        # weight 3.0 - near-unique to the type
    supporting: tuple[str, ...] = ()    # weight 1.5
    weak: tuple[str, ...] = ()          # weight 0.6
    negative: tuple[str, ...] = ()      # weight -2.0
    expects_line_items: bool = False
    expects_totals: bool = False
    typical_pages: tuple[int, int] = (1, 8)
    aspect_hint: str | None = None      # 'card' | 'portrait' | None


SIGNATURES: dict[str, TypeSignature] = {
    DocumentType.MEDICAL_INVOICE: TypeSignature(
        DocumentType.MEDICAL_INVOICE,
        strong=("medical invoice", "tax invoice", "patient name", "consultation fee",
                "invoice no", "invoice number", "medical services"),
        supporting=("diagnosis", "physician", "treatment", "hospital", "clinic", "icd",
                    "attending", "procedure", "consultation"),
        weak=("subtotal", "total", "tax", "vat", "gst", "amount due", "patient"),
        negative=("prescription only", "police report", "repair estimate"),
        expects_line_items=True, expects_totals=True,
    ),
    DocumentType.HOSPITAL_BILL: TypeSignature(
        DocumentType.HOSPITAL_BILL,
        strong=("hospital bill", "inpatient bill", "final bill", "bill of supply",
                "admission date", "discharge date", "bed charges", "room charges"),
        supporting=("ward", "nursing", "icu", "pharmacy charges", "operation theatre",
                    "inpatient", "ip no", "uhid"),
        weak=("hospital", "patient", "total", "charges"),
        expects_line_items=True, expects_totals=True,
    ),
    DocumentType.PRESCRIPTION: TypeSignature(
        DocumentType.PRESCRIPTION,
        strong=("prescription", "rx", "sig.", "dispense", "refill", "tablets", "dosage"),
        supporting=("mg", "twice daily", "once daily", "bd", "tds", "od", "capsule",
                    "syrup", "prescriber"),
        weak=("doctor", "patient", "date"),
        negative=("invoice total", "amount due", "grand total"),
        typical_pages=(1, 2),
    ),
    DocumentType.IDENTITY_DOCUMENT: TypeSignature(
        DocumentType.IDENTITY_DOCUMENT,
        strong=("identity card", "national id", "passport", "driving licence",
                "driver license", "driving license", "date of birth", "place of birth",
                "nationality", "id no"),
        supporting=("issuing authority", "sex", "gender", "expiry", "holder signature",
                    "machine readable"),
        weak=("address", "issued"),
        negative=("invoice", "total due", "line items"),
        typical_pages=(1, 2), aspect_hint="card",
    ),
    DocumentType.INSURANCE_CERTIFICATE: TypeSignature(
        DocumentType.INSURANCE_CERTIFICATE,
        strong=("certificate of insurance", "insurance certificate", "policy schedule",
                "sum insured", "period of insurance", "certificate no"),
        supporting=("insurer", "underwriter", "coverage", "premium", "policy number",
                    "beneficiary", "endorsement"),
        weak=("valid from", "valid to", "policy"),
    ),
    DocumentType.CLAIM_FORM: TypeSignature(
        DocumentType.CLAIM_FORM,
        strong=("claim form", "claim application", "declaration by the insured",
                "claimant declaration", "part a", "part b", "claim no"),
        supporting=("signature of insured", "bank details for settlement", "nominee",
                    "relationship to insured", "nature of claim", "date of loss"),
        weak=("policy number", "claim", "declaration"),
    ),
    DocumentType.VEHICLE_DOCUMENT: TypeSignature(
        DocumentType.VEHICLE_DOCUMENT,
        strong=("certificate of registration", "vehicle registration", "chassis no",
                "engine no", "vin", "registration certificate", "rc book"),
        supporting=("make", "model", "fuel type", "seating capacity", "owner name",
                    "registration authority", "cubic capacity"),
        weak=("vehicle", "colour", "class of vehicle"),
    ),
    DocumentType.REPAIR_ESTIMATE: TypeSignature(
        DocumentType.REPAIR_ESTIMATE,
        strong=("repair estimate", "damage estimate", "estimate of repairs", "labour charges",
                "labor charges", "parts list", "body shop", "panel beating", "paint labour"),
        supporting=("garage", "workshop", "spare parts", "odometer", "estimate no",
                    "assessor", "surveyor"),
        weak=("parts", "labour", "total", "vehicle"),
        expects_line_items=True, expects_totals=True,
    ),
    DocumentType.RECEIPT: TypeSignature(
        DocumentType.RECEIPT,
        strong=("receipt", "payment receipt", "cash receipt", "received with thanks",
                "receipt no", "paid in full"),
        supporting=("payment method", "card ending", "cash", "change due", "transaction id",
                    "terminal id", "merchant"),
        weak=("total", "tax", "thank you"),
        typical_pages=(1, 3), expects_totals=True,
    ),
    DocumentType.POLICE_REPORT: TypeSignature(
        DocumentType.POLICE_REPORT,
        strong=("police report", "first information report", "fir no", "police station",
                "investigating officer", "accident report", "general diary"),
        supporting=("complainant", "witness", "statement", "offence", "jurisdiction",
                    "constable", "inspector"),
        weak=("incident", "location", "date of incident"),
    ),
    DocumentType.BANK_PAYMENT_DOCUMENT: TypeSignature(
        DocumentType.BANK_PAYMENT_DOCUMENT,
        strong=("bank statement", "account statement", "payment advice", "remittance advice",
                "neft", "swift", "utr no", "ifsc", "iban", "sort code"),
        supporting=("account number", "opening balance", "closing balance", "beneficiary",
                    "value date", "transaction reference"),
        weak=("credit", "debit", "balance", "bank"),
        expects_line_items=True,
    ),
}

TYPE_ORDER = list(SIGNATURES.keys()) + [DocumentType.OTHER]
