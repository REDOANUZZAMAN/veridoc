"""OCR routing, classification and schema-driven field extraction."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.classify.classifier import classify
from app.services.extract.engine import extract_fields
from app.services.extract.normalize import (
    is_same_person,
    normalize_identifier,
    normalize_name,
    parse_date,
    parse_money,
    person_similarity,
)
from app.services.extract.schema import schema_for
from app.services.ocr.base import OcrTarget
from app.services.ocr.factory import get_ocr_provider, list_ocr_providers
from app.services.render import render_document
from app.services.storage.factory import get_storage


def run_ocr(data: bytes, mime: str, prefix: str):
    storage = get_storage()
    pages = render_document(data, mime, prefix, storage)
    provider = get_ocr_provider()
    results = [
        provider.extract(OcrTarget(
            page_number=page.page_number, image_bytes=page.png_bytes, width=page.width,
            height=page.height, pdf_bytes=data if mime == "application/pdf" else None,
            artifact_prefix=prefix,
        ))
        for page in pages
    ]
    return pages, results


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,234.56", Decimal("1234.56")),
        ("1.234,56 EUR", Decimal("1234.56")),
        ("(250.00)", Decimal("-250.00")),
        ("USD 8,500", Decimal("8500")),
        ("no digits here", None),
    ],
)
def test_money_parsing(raw, expected):
    assert parse_money(raw)[0] == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-08-15", date(2026, 8, 15)),
        ("15/08/2026", date(2026, 8, 15)),
        ("15 Aug 2026", date(2026, 8, 15)),
        ("August 15, 2026", date(2026, 8, 15)),
        ("not a date", None),
    ],
)
def test_date_parsing(raw, expected):
    assert parse_date(raw) == expected


def test_identifier_and_name_normalisation():
    assert normalize_identifier("pol-938 472") == "POL938472"
    assert normalize_name("Dr. Amelia R. Okonkwo") == "amelia r okonkwo"


def test_same_person_distinguishes_a_dependant_from_the_policyholder():
    # A shared surname is not identity - this distinction drives whether a
    # date of birth may be compared against the policy register at all.
    assert person_similarity("Amelia R. Okonkwo", "AMELIA R OKONKWO") > 0.95
    assert not is_same_person("Daniel Okonkwo", "Amelia R. Okonkwo")


def test_ocr_providers_are_discoverable():
    keys = {provider["key"] for provider in list_ocr_providers()}
    assert {"hybrid", "tesseract", "pdf_text", "demo_fixture"} <= keys


def test_pdf_text_layer_is_used_for_digital_pdfs(invoice_pdf):
    data, mime = invoice_pdf
    _, results = run_ocr(data, mime, "tests/ocr-route")
    assert results[0].engine_detail["route"] == "pdf_text_layer"
    assert results[0].mean_confidence > 0.9
    assert results[0].word_count > 40
    assert all(word.bbox.width > 0 for word in results[0].words)


def test_classifier_identifies_a_medical_invoice(invoice_pdf):
    data, mime = invoice_pdf
    pages, results = run_ocr(data, mime, "tests/cls")
    result = classify("\n".join(r.text for r in results), page_count=len(pages),
                      page_sizes=[(p.width, p.height) for p in pages])
    assert result.document_type == "medical_invoice"
    assert 0.5 < result.confidence <= 0.985
    assert result.matched_terms  # explainable: the terms that drove the decision


def test_classifier_is_not_confident_about_noise():
    result = classify("lorem ipsum dolor sit amet " * 20)
    assert result.document_type == "other"
    assert result.confidence < 0.5


def test_field_extraction_finds_values_with_boxes_and_confidence(invoice_pdf):
    data, mime = invoice_pdf
    _, results = run_ocr(data, mime, "tests/extract")
    extraction = extract_fields(results, schema_for("medical_invoice"))
    values = {f.key: f.value_normalized for f in extraction.fields}

    assert values["invoice_number"] == "MGH2026004417"
    assert values["invoice_date"] == "2026-08-18"
    assert values["treatment_date"] == "2026-08-15"
    assert values["total"] == "4820.00"
    assert values["subtotal"] == "4820.00"
    assert values["patient_name"] == "Amelia R. Okonkwo"
    assert values["hospital_name"] == "Meridian General Hospital"
    assert not extraction.missing_required
    assert len(extraction.line_items) == 3
    assert all(f.bbox and f.bbox["width"] > 0 for f in extraction.fields if f.page)


def test_requiredness_is_per_document_type():
    # A bank payment advice has no total; an invoice must have one.
    assert "total" in schema_for("medical_invoice").required_keys()
    assert "total" not in schema_for("bank_payment_document").required_keys()
    assert schema_for("other").required_keys() == []


def test_label_inside_a_heading_is_not_treated_as_a_field():
    """'HOSPITAL BILL' as a title must not yield hospital_name = 'BILL'."""
    from app.db.demo_documents import DocSpec, render

    spec = DocSpec(
        key="t", kind="pdf", title="Hospital Bill", organisation="Lakeside Wellness Clinic",
        party_fields=[("Patient name", "Priya Raghunathan")],
        header_fields=[("Bill number", "LWC-2026-0219"), ("Invoice date", "2026-06-28")],
        items=[("Bed charges", "3", "320.00", "960.00")],
        totals=[("Subtotal", "$960.00"), ("Total amount", "$960.00")], seed=9,
    )
    data, _, mime = render(spec)
    _, results = run_ocr(data, mime, "tests/heading")
    extraction = extract_fields(results, schema_for("hospital_bill"))
    values = {f.key: f.value_normalized for f in extraction.fields}
    assert values.get("hospital_name") == "Lakeside Wellness Clinic"
    assert values.get("invoice_number") == "LWC20260219"
