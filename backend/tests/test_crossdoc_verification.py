"""Cross-document comparison and trusted-source verification."""
from __future__ import annotations

import pytest

from app.core.errors import ProviderUnavailable
from app.services.crossdoc.engine import DocumentSnapshot, compare_documents
from app.services.verification.base import VerificationQuery, outcome_from_checks
from app.services.verification.factory import (
    get_verification_provider,
    list_verification_providers,
)
from app.services.verification.remote_http import RemoteHttpVerificationProvider


def snapshot(ref, doc_type, **fields):
    return DocumentSnapshot(
        document_id=f"id-{ref}", document_ref=ref, document_type=doc_type,
        label=doc_type.replace("_", " ").title(),
        fields={k: {"value": v, "raw": v, "confidence": 0.95, "page": 1,
                    "bbox": {"x": 1, "y": 1, "width": 10, "height": 10}}
                for k, v in fields.items()},
    )


def test_total_mismatch_between_invoice_and_claim_form():
    invoice = snapshot("DOC-1", "medical_invoice", total="8500.00",
                       patient_name="Amelia R. Okonkwo", invoice_number="MGH-1")
    form = snapshot("DOC-2", "claim_form", total="6500.00",
                    patient_name="Amelia R. Okonkwo")
    report = compare_documents([invoice, form])
    codes = {f.finding.code for f in report.findings}
    assert "XDOC_TOTAL_MISMATCH" in codes
    finding = next(f for f in report.findings if f.finding.code == "XDOC_TOTAL_MISMATCH")
    assert finding.value_a == "8500.00" and finding.value_b == "6500.00"
    assert finding.finding.severity == "high"


def test_two_unrelated_invoices_are_not_compared_on_total():
    a = snapshot("DOC-1", "medical_invoice", total="500.00", invoice_number="INV-1",
                 patient_name="Amelia R. Okonkwo")
    b = snapshot("DOC-2", "medical_invoice", total="900.00", invoice_number="INV-2",
                 patient_name="Amelia R. Okonkwo")
    report = compare_documents([a, b])
    assert all(f.finding.code != "XDOC_TOTAL_MISMATCH" for f in report.findings)
    skipped = [c for c in report.comparisons if c["field"] == "total" and c.get("skipped")]
    assert skipped and "separate transactions" in skipped[0]["detail"]


def test_dependant_date_of_birth_is_not_compared_with_the_policyholders():
    invoice = snapshot("DOC-1", "medical_invoice", patient_name="Daniel Okonkwo",
                       date_of_birth="2014-03-09", insured_name="Amelia R. Okonkwo")
    identity = snapshot("DOC-2", "identity_document", customer_name="Amelia R. Okonkwo",
                        date_of_birth="1986-04-12")
    report = compare_documents([invoice, identity], claim={
        "claim_number": "CLM-1", "customer_name": "Amelia R. Okonkwo",
        "customer_dob": "1986-04-12",
    })
    assert all("DATE_OF_BIRTH" not in f.finding.code for f in report.findings)
    skipped = [c for c in report.comparisons
               if c["field"] == "date_of_birth" and c.get("skipped")]
    assert skipped


def test_policy_number_mismatch_against_the_claim_record():
    invoice = snapshot("DOC-1", "medical_invoice", policy_number="POL-111111",
                       insured_name="Amelia R. Okonkwo")
    report = compare_documents([invoice], claim={
        "claim_number": "CLM-1", "policy_number": "POL-938472",
        "customer_name": "Amelia R. Okonkwo",
    })
    codes = {f.finding.code for f in report.findings}
    assert "XDOC_CLAIM_POLICY_NUMBER_MISMATCH" in codes


def test_identical_values_produce_no_findings():
    a = snapshot("DOC-1", "medical_invoice", policy_number="POL-938472",
                 patient_name="Amelia R. Okonkwo", hospital_name="Meridian General Hospital")
    b = snapshot("DOC-2", "prescription", policy_number="POL-938472",
                 patient_name="Amelia R Okonkwo", hospital_name="Meridian General Hospital")
    report = compare_documents([a, b])
    assert report.findings == []
    assert report.summary()["mismatches"] == 0


def test_single_document_without_a_claim_produces_nothing():
    report = compare_documents([snapshot("DOC-1", "medical_invoice", total="10.00")])
    assert report.findings == [] and report.comparisons == []


# --------------------------------------------------------------------- verification
def test_demo_providers_are_labelled_as_demo():
    providers = list_verification_providers()
    demo = [p for p in providers if p["mode"] == "demo"]
    assert len(demo) >= 6
    assert all(p["is_demo"] for p in demo)
    assert any(p["key"] == "remote_http" and not p["is_demo"] for p in providers)


def test_policy_lookup_match_carries_the_demo_disclaimer():
    provider = get_verification_provider("policy_lookup")
    response = provider.verify(VerificationQuery(
        request_type="policy_lookup",
        payload={"policy_number": "POL-938472", "insured_name": "Amelia R. Okonkwo",
                 "service_date": "2026-08-15", "total": "4820.00"},
    ))
    assert response.outcome == "match"
    assert response.is_demo_data is True
    assert "DEMO VERIFICATION PROVIDER" in response.disclaimer
    assert all(check.passed is not False for check in response.checks)


def test_lapsed_policy_outside_cover_is_a_mismatch():
    provider = get_verification_provider("policy_lookup")
    response = provider.verify(VerificationQuery(
        request_type="policy_lookup",
        payload={"policy_number": "POL-770311", "insured_name": "Priya Raghunathan",
                 "service_date": "2026-06-28"},
    ))
    assert response.outcome == "mismatch"
    failed = {check.key for check in response.failed_checks}
    assert {"policy_active", "date_in_cover"} <= failed


def test_unknown_policy_is_not_found():
    provider = get_verification_provider("policy_lookup")
    response = provider.verify(VerificationQuery(
        request_type="policy_lookup", payload={"policy_number": "POL-000000"}))
    assert response.outcome == "not_found"
    assert response.checks[0].passed is False


def test_invoice_amount_mismatch_is_reported_against_the_issuer_record():
    provider = get_verification_provider("invoice_lookup")
    response = provider.verify(VerificationQuery(
        request_type="invoice_lookup",
        payload={"invoice_number": "MGH-2026-004918", "total": "8500.00",
                 "invoice_date": "2026-08-27", "patient_name": "Amelia R. Okonkwo"},
    ))
    assert response.outcome == "mismatch"
    assert any(c.key == "amount_match" and c.passed is False for c in response.checks)


def test_vehicle_write_off_marker_is_surfaced():
    provider = get_verification_provider("vehicle_lookup")
    response = provider.verify(VerificationQuery(
        request_type="vehicle_lookup",
        payload={"vehicle_registration": "RTX-9081", "customer_name": "Priya Raghunathan"},
    ))
    assert response.outcome == "mismatch"
    assert any(c.key == "no_write_off_marker" and c.passed is False for c in response.checks)


def test_identity_reported_lost_is_a_mismatch():
    provider = get_verification_provider("identity_lookup")
    response = provider.verify(VerificationQuery(
        request_type="identity_lookup",
        payload={"national_id": "PN-9930012", "customer_name": "Priya Raghunathan",
                 "date_of_birth": "1991-07-22"},
    ))
    assert response.outcome == "mismatch"
    assert any(c.key == "document_valid" and c.passed is False for c in response.checks)


def test_dependant_date_of_birth_is_not_evaluated_against_the_policyholder():
    provider = get_verification_provider("policy_lookup")
    response = provider.verify(VerificationQuery(
        request_type="policy_lookup",
        payload={"policy_number": "POL-938472", "insured_name": "Amelia R. Okonkwo",
                 "patient_name": "Daniel Okonkwo", "date_of_birth": "2014-03-09",
                 "service_date": "2026-08-15"},
    ))
    dob = next(c for c in response.checks if c.key == "dob_match")
    assert dob.passed is None
    assert "not to the policyholder" in dob.note
    assert response.outcome == "match"


def test_remote_provider_raises_when_unconfigured():
    provider = RemoteHttpVerificationProvider(url=None, api_key=None)
    available, detail = provider.available()
    assert available is False and "not configured" in detail
    with pytest.raises(ProviderUnavailable):
        provider.verify(VerificationQuery(request_type="policy_lookup", payload={}))


def test_outcome_grading_treats_a_critical_check_as_a_mismatch():
    from app.services.verification.base import VerificationCheck

    checks = [
        VerificationCheck("record_exists", "Exists", "x", "x", True),
        VerificationCheck("policy_active", "Active", "active", "lapsed", False),
        VerificationCheck("dob_match", "DOB", "a", "a", True),
    ]
    assert outcome_from_checks(checks, found=True) == "mismatch"


def test_outcome_grading_treats_a_minor_check_as_partial():
    from app.services.verification.base import VerificationCheck

    checks = [
        VerificationCheck("record_exists", "Exists", "x", "x", True),
        VerificationCheck("invoice_prefix", "Prefix", "MGH-", "XXX-", False),
    ]
    assert outcome_from_checks(checks, found=True) == "partial_match"
