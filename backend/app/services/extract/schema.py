"""Declarative document schema.

Field extraction is *data driven*: a document type is a list of
:class:`FieldSpec` entries, each with label synonyms and a value pattern. Adding
a new document type (or a new locale's wording) means editing this registry -
no extractor code changes, and nothing is hard-coded around one sample invoice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ValueType = Literal["string", "money", "date", "identifier", "number", "percent", "list"]


@dataclass(slots=True)
class FieldSpec:
    key: str
    label: str
    value_type: ValueType = "string"
    # Label synonyms as they appear on real documents (case-insensitive).
    labels: tuple[str, ...] = ()
    # Optional direct value patterns, used when a document carries the value
    # without a printed label (e.g. an invoice number in a header line).
    patterns: tuple[str, ...] = ()
    required: bool = False
    group: str = "general"
    max_chars: int = 200
    allow_next_line: bool = True
    sensitive: bool = False

    def compiled_labels(self) -> list[re.Pattern]:
        """Label patterns that record whether a separator followed the label.

        The separator (or, failing that, a column gap) is what distinguishes a
        real labelled field from the same word appearing in a heading.
        """
        out = []
        for lab in self.labels:
            out.append(re.compile(
                rf"(?<![A-Za-z]){re.escape(lab)}\s*(?P<sep>[:#=])?\s*", re.I
            ))
        return out


F = FieldSpec

# --- reusable field library ---------------------------------------------------
FIELD_LIBRARY: dict[str, FieldSpec] = {
    f.key: f
    for f in [
        F("patient_name", "Patient Name", "string", ("patient name", "patient", "name of patient"),
          required=True, group="party", sensitive=True),
        F("insured_name", "Insured / Member Name", "string",
          ("insured name", "member name", "policy holder", "policyholder", "insured"),
          group="party", sensitive=True),
        F("customer_name", "Customer / Holder Name", "string",
          ("customer name", "customer", "client name", "full name", "holder name",
           "name of holder", "account holder", "registered keeper", "keeper name"),
          group="party", sensitive=True),
        F("date_of_birth", "Date of Birth", "date", ("date of birth", "dob", "d.o.b", "birth date"),
          group="party", sensitive=True),
        F("national_id", "National ID / Document No.", "identifier",
          ("national id", "id number", "document no", "document number", "passport no",
           "passport number", "licence no", "license no"),
          group="identity", sensitive=True),
        F("gender", "Gender", "string", ("gender", "sex"), group="party"),
        F("address", "Address", "string", ("address", "residential address", "billing address"),
          group="party", max_chars=240, sensitive=True),

        F("hospital_name", "Hospital / Provider", "string",
          ("hospital", "hospital name", "provider", "provider name", "facility", "clinic"),
          required=True, group="provider"),
        F("provider_registration", "Provider Registration No.", "identifier",
          ("registration no", "provider id", "facility code", "hospital reg"), group="provider"),
        F("department", "Department", "string", ("department", "ward", "unit"), group="provider"),
        F("physician_name", "Attending Physician", "string",
          ("physician", "doctor", "attending doctor", "consultant", "attending physician"),
          group="provider"),

        F("invoice_number", "Invoice Number", "identifier",
          ("invoice number", "invoice no", "invoice #", "bill number", "bill no", "inv no"),
          patterns=(r"\bINV[-/ ]?(?=[A-Z0-9/-]*\d)[A-Z0-9/-]{3,}\b",
                    r"\bBILL[-/ ]?(?=[A-Z0-9/-]*\d)[A-Z0-9/-]{3,}\b"),
          required=True, group="document"),
        F("invoice_date", "Invoice Date", "date",
          ("invoice date", "bill date", "date of invoice", "issued on", "issue date"),
          required=True, group="document"),
        F("treatment_date", "Treatment Date", "date",
          ("treatment date", "date of treatment", "service date", "date of service",
           "consultation date"),
          group="clinical"),
        F("admission_date", "Admission Date", "date", ("admission date", "admitted on", "date admitted"),
          group="clinical"),
        F("discharge_date", "Discharge Date", "date", ("discharge date", "discharged on"),
          group="clinical"),
        F("diagnosis", "Diagnosis", "string", ("diagnosis", "icd", "condition", "impression"),
          group="clinical", max_chars=240, sensitive=True),
        F("procedure", "Procedure", "string", ("procedure", "treatment", "surgery"),
          group="clinical", sensitive=True),

        F("policy_number", "Policy Number", "identifier",
          ("policy number", "policy no", "policy #", "certificate no", "member no"),
          patterns=(r"\bPOL[-/ ]?(?=[A-Z0-9/-]*\d)[A-Z0-9/-]{3,}\b",), group="policy"),
        F("claim_number", "Claim Number", "identifier",
          ("claim number", "claim no", "claim reference", "claim ref", "claim id"),
          patterns=(r"\bCLM[- ]?[0-9]{4}[- ]?[0-9]{3,}\b",), group="policy"),
        F("insurer_name", "Insurer", "string", ("insurer", "insurance company", "underwriter"),
          group="policy"),
        F("coverage_amount", "Coverage Amount", "money",
          ("coverage amount", "sum insured", "coverage limit", "benefit limit"), group="policy"),
        F("valid_from", "Valid From", "date", ("valid from", "effective date", "cover start"),
          group="policy"),
        F("valid_to", "Valid To", "date", ("valid to", "expiry date", "expires on", "cover end",
                                           "valid until"), group="policy"),

        F("currency", "Currency", "string", ("currency",), patterns=(r"\b(USD|EUR|GBP|SGD|AUD|INR|BDT)\b",),
          group="amounts"),
        F("subtotal", "Subtotal", "money", ("subtotal", "sub total", "net amount", "amount before tax"),
          group="amounts"),
        F("discount", "Discount", "money", ("discount", "less discount", "rebate"), group="amounts"),
        F("tax", "Tax", "money", ("tax", "vat", "gst", "sales tax", "service tax"), group="amounts"),
        F("tax_rate", "Tax Rate", "percent", ("tax rate", "vat rate", "gst rate"), group="amounts"),
        F("total", "Total Amount", "money",
          ("total amount", "grand total", "total due", "amount due", "total payable", "total"),
          required=True, group="amounts"),
        F("amount_paid", "Amount Paid", "money", ("amount paid", "paid", "payment received"),
          group="amounts"),
        F("balance_due", "Balance Due", "money", ("balance due", "outstanding", "balance"),
          group="amounts"),

        F("receipt_number", "Receipt Number", "identifier",
          ("receipt number", "receipt no", "receipt #", "transaction no"), group="document"),
        F("payment_method", "Payment Method", "string",
          ("payment method", "paid by", "payment mode", "tender"), group="payment"),
        F("bank_name", "Bank", "string", ("bank", "bank name", "issuing bank"), group="payment"),
        F("account_number", "Account Number", "identifier",
          ("account number", "account no", "a/c no", "iban"), group="payment", sensitive=True),
        F("transaction_reference", "Transaction Reference", "identifier",
          ("transaction reference", "transaction id", "reference no", "utr", "payment ref"),
          group="payment"),

        F("prescriber_name", "Prescriber", "string",
          ("prescriber", "prescribed by", "doctor", "physician"), group="clinical"),
        F("prescription_date", "Prescription Date", "date",
          ("prescription date", "date prescribed", "rx date"), group="clinical"),
        F("prescription_number", "Prescription Number", "identifier",
          ("prescription no", "rx no", "rx number", "prescription number"), group="document"),

        F("vehicle_registration", "Vehicle Registration", "identifier",
          ("registration number", "reg no", "registration no", "licence plate", "license plate",
           "plate no", "vehicle no"), group="vehicle"),
        F("vin", "VIN / Chassis Number", "identifier",
          ("vin", "chassis no", "chassis number", "vehicle identification number"), group="vehicle"),
        F("vehicle_make", "Make", "string", ("make", "manufacturer"), group="vehicle"),
        F("vehicle_model", "Model", "string", ("model", "variant"), group="vehicle"),
        F("vehicle_year", "Year", "number", ("year", "year of manufacture", "model year"),
          group="vehicle"),
        F("odometer", "Odometer", "number", ("odometer", "mileage", "km reading"), group="vehicle"),

        F("estimate_number", "Estimate Number", "identifier",
          ("estimate no", "estimate number", "quotation no", "quote no", "job no"),
          group="document"),
        F("parts_total", "Parts Total", "money", ("parts total", "total parts", "parts"),
          group="amounts"),
        F("labour_total", "Labour Total", "money",
          ("labour total", "labor total", "total labour", "total labor", "labour charges"),
          group="amounts"),
        F("garage_name", "Repairer / Garage", "string",
          ("garage", "repairer", "workshop", "body shop", "service centre", "service center"),
          group="provider"),

        F("report_number", "Report Number", "identifier",
          ("report no", "report number", "fir no", "case no", "incident no"), group="document"),
        F("incident_date", "Incident Date", "date",
          ("incident date", "date of incident", "date of accident", "accident date",
           "date of loss"), group="incident"),
        F("incident_location", "Incident Location", "string",
          ("location", "place of incident", "accident location"), group="incident", max_chars=240),
        F("officer_name", "Reporting Officer", "string",
          ("officer", "reporting officer", "investigating officer"), group="incident"),

        F("certificate_number", "Certificate Number", "identifier",
          ("certificate number", "certificate no", "cert no"), group="document"),
        F("issue_date", "Issue Date", "date", ("issue date", "issued on", "date of issue"),
          group="document"),
        F("expiry_date", "Expiry Date", "date", ("expiry date", "expires on", "date of expiry",
                                                  "valid until"), group="document"),
        F("issuing_authority", "Issuing Authority", "string",
          ("issuing authority", "issued by", "authority"), group="identity"),
    ]
}


@dataclass(slots=True)
class DocumentSchema:
    document_type: str
    label: str
    field_keys: tuple[str, ...]
    # Requiredness is a property of the document *type*, not of the field: an
    # invoice must carry a total, a police report must not.
    required: tuple[str, ...] | None = None
    line_items: bool = False
    line_item_label: str = "Line Items"
    notes: str = ""

    @property
    def fields(self) -> list[FieldSpec]:
        return [FIELD_LIBRARY[k] for k in self.field_keys if k in FIELD_LIBRARY]

    def required_keys(self) -> list[str]:
        if self.required is not None:
            return [k for k in self.required if k in self.field_keys]
        return [f.key for f in self.fields if f.required]

    def is_required(self, key: str) -> bool:
        return key in set(self.required_keys())


_COMMON_AMOUNTS = ("currency", "subtotal", "discount", "tax", "tax_rate", "total")

SCHEMAS: dict[str, DocumentSchema] = {
    "medical_invoice": DocumentSchema(
        "medical_invoice", "Medical Invoice",
        ("patient_name", "insured_name", "date_of_birth", "hospital_name", "physician_name",
         "department", "invoice_number", "invoice_date", "treatment_date", "diagnosis",
         "procedure", "policy_number", "claim_number", *_COMMON_AMOUNTS, "amount_paid",
         "balance_due"),
        required=("patient_name", "hospital_name", "invoice_number", "invoice_date", "total"),
        line_items=True, line_item_label="Billed Items",
    ),
    "hospital_bill": DocumentSchema(
        "hospital_bill", "Hospital Bill",
        ("patient_name", "date_of_birth", "hospital_name", "provider_registration", "department",
         "invoice_number", "invoice_date", "admission_date", "discharge_date", "diagnosis",
         "policy_number", *_COMMON_AMOUNTS, "amount_paid", "balance_due"),
        required=("patient_name", "hospital_name", "invoice_number", "invoice_date", "total"),
        line_items=True, line_item_label="Charge Lines",
    ),
    "prescription": DocumentSchema(
        "prescription", "Prescription",
        ("patient_name", "date_of_birth", "prescriber_name", "hospital_name",
         "prescription_number", "prescription_date", "diagnosis"),
        required=("patient_name", "prescription_date"),
        line_items=True, line_item_label="Prescribed Medication",
    ),
    "identity_document": DocumentSchema(
        "identity_document", "Identity Document",
        ("customer_name", "date_of_birth", "gender", "national_id", "address",
         "issuing_authority", "issue_date", "expiry_date"),
        required=("customer_name", "national_id", "date_of_birth"),
    ),
    "insurance_certificate": DocumentSchema(
        "insurance_certificate", "Insurance Certificate",
        ("insured_name", "insurer_name", "policy_number", "certificate_number",
         "coverage_amount", "currency", "valid_from", "valid_to", "issue_date", "address"),
        required=("insured_name", "policy_number"),
    ),
    "claim_form": DocumentSchema(
        "claim_form", "Claim Form",
        ("claim_number", "policy_number", "insured_name", "patient_name", "date_of_birth",
         "hospital_name", "treatment_date", "incident_date", "diagnosis", "currency", "total",
         "bank_name", "account_number"),
        required=("policy_number", "insured_name"),
    ),
    "vehicle_document": DocumentSchema(
        "vehicle_document", "Vehicle Document",
        ("customer_name", "vehicle_registration", "vin", "vehicle_make", "vehicle_model",
         "vehicle_year", "issuing_authority", "issue_date", "expiry_date", "address"),
        required=("vehicle_registration",),
    ),
    "repair_estimate": DocumentSchema(
        "repair_estimate", "Repair Estimate",
        ("customer_name", "garage_name", "estimate_number", "invoice_date", "incident_date",
         "vehicle_registration", "vin", "vehicle_make", "vehicle_model", "odometer",
         "parts_total", "labour_total", *_COMMON_AMOUNTS, "claim_number", "policy_number"),
        required=("vehicle_registration", "total"),
        line_items=True, line_item_label="Repair Operations",
    ),
    "receipt": DocumentSchema(
        "receipt", "Receipt",
        ("receipt_number", "invoice_number", "invoice_date", "hospital_name", "garage_name",
         "patient_name", "customer_name", "payment_method", "currency",
         "subtotal", "tax", "total", "amount_paid", "transaction_reference"),
        required=("total", "invoice_date"),
        line_items=True,
    ),
    "police_report": DocumentSchema(
        "police_report", "Police Report",
        ("report_number", "incident_date", "incident_location", "officer_name", "customer_name",
         "vehicle_registration", "issue_date"),
        required=("report_number", "incident_date"),
    ),
    "bank_payment_document": DocumentSchema(
        "bank_payment_document", "Bank / Payment Document",
        ("bank_name", "account_number", "customer_name", "transaction_reference", "invoice_date",
         "currency", "amount_paid", "payment_method"),
        required=("transaction_reference",),
        line_items=True, line_item_label="Transactions",
    ),
    "other": DocumentSchema(
        "other", "Other",
        ("customer_name", "invoice_number", "invoice_date", "currency", "total"),
        # An unclassified document has no contract to violate.
        required=(),
    ),
}


def schema_for(document_type: str | None) -> DocumentSchema:
    return SCHEMAS.get(document_type or "other", SCHEMAS["other"])
