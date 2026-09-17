"""Consistency rule engine: each rule in isolation, plus engine behaviour."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.consistency.engine import (
    effective_config,
    rule_catalogue,
    run_consistency,
)
from app.services.consistency.rules import REGISTRY, RuleContext, rules_for
from app.services.extract.engine import ExtractionResult, FieldValue, LineItem


def field(key, value, value_type="string", **kw):
    return FieldValue(
        key=key, label=key.replace("_", " ").title(), value_type=value_type,
        value_raw=str(value), value_normalized=str(value), confidence=kw.pop("confidence", 0.95),
        page=1, bbox={"x": 10, "y": 10, "width": 80, "height": 12, "unit": "render_px"},
        source="ocr", required=kw.pop("required", False), group=kw.pop("group", "general"),
    )


def item(index, description, amount):
    return LineItem(index=index, description=description, quantity=None, unit_price=None,
                    amount=Decimal(str(amount)), page=1, bbox=None, raw=description)


def context(fields, items=(), document_type="medical_invoice", required=()):
    return RuleContext(
        document_type=document_type, fields={f.key: f for f in fields}, line_items=list(items),
        page_texts={1: " ".join(f.value_raw for f in fields)},
        required_keys=list(required), today=date(2026, 9, 17),
    )


def run_rule(code, ctx):
    rule = next(r for r in REGISTRY if r.code == code)
    return rule.fn(ctx, effective_config(rule, None))


def test_line_item_sum_mismatch_detected():
    ctx = context([field("subtotal", "4500.00", "money")],
                  [item(1, "A", 1500), item(2, "B", 1000), item(3, "C", 800)])
    findings = run_rule("LINE_ITEM_SUM_MISMATCH", ctx)
    assert len(findings) == 1
    assert findings[0].extras["expected"] == "3300"
    assert findings[0].extras["actual"] == "4500.00"
    assert findings[0].severity == "high"


def test_line_item_sum_passes_when_it_reconciles():
    ctx = context([field("subtotal", "3300.00", "money")],
                  [item(1, "A", 1500), item(2, "B", 1000), item(3, "C", 800)])
    assert run_rule("LINE_ITEM_SUM_MISMATCH", ctx) == []


def test_total_arithmetic_mismatch_detected():
    ctx = context([field("subtotal", "6500.00", "money"), field("tax", "0.00", "money"),
                   field("total", "8500.00", "money")])
    findings = run_rule("TOTAL_ARITHMETIC_MISMATCH", ctx)
    assert len(findings) == 1
    assert "8500.00" in findings[0].evidence["stated_total"]


def test_tax_calculation_mismatch_detected():
    ctx = context([field("subtotal", "600.00", "money"), field("tax", "96.00", "money"),
                   field("tax_rate", "8", "percent")])
    findings = run_rule("TAX_CALCULATION_MISMATCH", ctx)
    assert len(findings) == 1
    assert findings[0].evidence["expected_tax"] == "48.00"


def test_treatment_after_invoice_detected():
    ctx = context([field("invoice_date", "2026-09-01", "date"),
                   field("treatment_date", "2026-09-05", "date")])
    findings = run_rule("TREATMENT_AFTER_INVOICE", ctx)
    assert len(findings) == 1
    assert findings[0].evidence["days_after"] == 4


def test_admission_after_discharge_detected():
    ctx = context([field("admission_date", "2026-06-28", "date"),
                   field("discharge_date", "2026-06-26", "date")])
    assert len(run_rule("ADMISSION_AFTER_DISCHARGE", ctx)) == 1


def test_future_dated_document_detected():
    ctx = context([field("invoice_date", "2027-01-01", "date")])
    findings = run_rule("FUTURE_DATED_DOCUMENT", ctx)
    assert findings and findings[0].evidence["days_ahead"] > 0


def test_vin_check_digit_rule():
    valid = context([field("vin", "WBA3A5C57FF123456", "identifier")],
                    document_type="vehicle_document")
    invalid = context([field("vin", "WBA3A5C51FF123456", "identifier")],
                      document_type="vehicle_document")
    assert run_rule("VIN_CHECK_DIGIT_INVALID", valid) == []
    findings = run_rule("VIN_CHECK_DIGIT_INVALID", invalid)
    assert len(findings) == 1
    assert findings[0].evidence["computed_check_digit"] == "7"


def test_iban_checksum_rule():
    good = context([field("account_number", "GB29NWBK60161331926819", "identifier")])
    bad = context([field("account_number", "GB29NWBK60161331926810", "identifier")])
    assert run_rule("IBAN_CHECKSUM_INVALID", good) == []
    assert len(run_rule("IBAN_CHECKSUM_INVALID", bad)) == 1


def test_duplicate_line_items_detected():
    ctx = context([], [item(1, "Front bumper", 1800), item(2, "Front bumper", 1800)])
    assert len(run_rule("DUPLICATE_LINE_ITEMS", ctx)) == 1


def test_currency_ambiguity_detected():
    ctx = context([field("total", "$100 and EUR 90", "string")])
    findings = run_rule("CURRENCY_AMBIGUOUS", ctx)
    assert findings and set(findings[0].evidence["currencies_detected"]) == {"USD", "EUR"}


def test_missing_required_field_reported():
    ctx = context([field("total", "100.00", "money")], required=["patient_name", "total"])
    findings = run_rule("MISSING_REQUIRED_FIELD", ctx)
    assert findings and findings[0].evidence["missing_fields"] == ["patient_name"]


def test_internal_name_mismatch_is_low_severity_with_an_explanation():
    ctx = context([field("patient_name", "Daniel Okonkwo"),
                   field("insured_name", "Amelia R. Okonkwo")])
    findings = run_rule("INTERNAL_NAME_MISMATCH", ctx)
    assert findings and findings[0].severity == "low"
    assert "dependant" in findings[0].description


def test_rule_returns_none_when_inputs_are_absent():
    assert run_rule("TOTAL_ARITHMETIC_MISMATCH", context([])) is None


def test_engine_reports_passed_and_failed_checks():
    extraction = ExtractionResult(
        document_type="medical_invoice",
        fields=[field("subtotal", "100.00", "money"), field("tax", "10.00", "money"),
                field("total", "200.00", "money"), field("invoice_date", "2026-08-01", "date"),
                field("invoice_number", "INV-1001", "identifier"),
                field("patient_name", "Amelia R. Okonkwo"),
                field("hospital_name", "Meridian General Hospital")],
        line_items=[], missing_required=[],
    )
    report = run_consistency(extraction, document_type="medical_invoice",
                             required_keys=["total"], today=date(2026, 9, 17))
    summary = report.summary()
    assert summary["failed"] >= 1
    assert summary["passed"] >= 1
    codes = {c["code"] for c in summary["checks"] if c["status"] == "failed"}
    assert "TOTAL_ARITHMETIC_MISMATCH" in codes


def test_engine_honours_a_disabled_rule():
    extraction = ExtractionResult(
        document_type="medical_invoice",
        fields=[field("subtotal", "100.00", "money"), field("total", "200.00", "money")],
        line_items=[], missing_required=[],
    )
    report = run_consistency(
        extraction, document_type="medical_invoice",
        rule_overrides={"TOTAL_ARITHMETIC_MISMATCH": {"enabled": False}},
    )
    assert all(f.code != "TOTAL_ARITHMETIC_MISMATCH" for f in report.findings)
    assert any(c["code"] == "TOTAL_ARITHMETIC_MISMATCH" and c["status"] == "disabled"
               for c in report.summary()["checks"])


def test_engine_honours_an_overridden_severity_and_weight():
    extraction = ExtractionResult(
        document_type="medical_invoice",
        fields=[field("subtotal", "100.00", "money"), field("total", "200.00", "money")],
        line_items=[], missing_required=[],
    )
    report = run_consistency(
        extraction, document_type="medical_invoice",
        rule_overrides={"TOTAL_ARITHMETIC_MISMATCH": {"severity": "low", "weight": 2.0}},
    )
    finding = next(f for f in report.findings if f.code == "TOTAL_ARITHMETIC_MISMATCH")
    assert finding.severity == "low"
    assert finding.extras["rule_weight"] == 2.0


def test_rules_are_scoped_by_document_type():
    codes = {r.code for r in rules_for("police_report")}
    assert "VIN_CHECK_DIGIT_INVALID" not in codes
    assert "VIN_CHECK_DIGIT_INVALID" in {r.code for r in rules_for("vehicle_document")}


def test_catalogue_is_complete_and_serialisable():
    catalogue = rule_catalogue()
    assert len(catalogue) == len(REGISTRY)
    assert all({"code", "name", "description", "default_severity", "weight"} <= set(entry)
               for entry in catalogue)


def test_a_broken_rule_does_not_fail_the_run(monkeypatch):
    rule = next(r for r in REGISTRY if r.code == "TOTAL_ARITHMETIC_MISMATCH")

    def explode(ctx, cfg):
        raise RuntimeError("boom")

    monkeypatch.setattr(rule, "fn", explode)
    extraction = ExtractionResult(document_type="medical_invoice", fields=[], line_items=[],
                                  missing_required=[])
    report = run_consistency(extraction, document_type="medical_invoice")
    assert any(c["status"] == "error" for c in report.summary()["checks"])
