"""End-to-end pipeline behaviour, including degraded providers."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import ProviderUnavailable
from app.db.models.analysis import AnalysisRun, RiskAssessment
from app.db.models.document import Document, DocumentPage, ExtractedField, OcrResult
from app.services import findings_store
from app.services.pipeline import STAGE_DEFINITIONS, run_analysis
from app.services.storage.factory import get_storage
from tests.conftest import upload

pytestmark = pytest.mark.slow


def _ingest(client, token, data, name, mime, claim_id):
    response = upload(client, token, data, name, mime, claim_id, analyze=False)
    assert response.status_code == 201, response.text
    return response.json()["document"]["id"]


def test_clean_invoice_completes_every_stage(client, claims_token, db, invoice_pdf, make_claim):
    data, mime = invoice_pdf
    claim = make_claim()
    document_id = _ingest(client, claims_token, data, "clean.pdf", mime, claim["id"])

    run = run_analysis(db, document_id)
    db.commit()

    statuses = {stage["key"]: stage["status"] for stage in run.stages}
    for key, _, critical in STAGE_DEFINITIONS:
        if critical:
            assert statuses[key] == "completed", f"{key} -> {statuses[key]}"
    assert run.status in ("analyzed", "partial")

    document = db.get(Document, document_id)
    assert document.classification_type == "medical_invoice"
    assert document.page_count == 1
    assert document.risk_band == "low_concern"
    assert document.malware_status == "clean"
    assert db.execute(select(OcrResult).where(
        OcrResult.document_id == document_id)).scalars().all()
    assert db.execute(select(ExtractedField).where(
        ExtractedField.document_id == document_id)).scalars().all()
    assert db.execute(select(RiskAssessment).where(
        RiskAssessment.document_id == document_id)).scalars().all()


def test_tampered_invoice_produces_the_expected_evidence(
    client, claims_token, db, tampered_invoice_pdf, make_claim
):
    data, mime = tampered_invoice_pdf
    claim = make_claim(claimed_amount="8500.00")
    document_id = _ingest(client, claims_token, data, "tampered.pdf", mime, claim["id"])
    run_analysis(db, document_id)
    db.commit()

    document = db.get(Document, document_id)
    codes = {f.code for f in findings_store.collect(db, document_id)}

    # The planted anomalies are each detected by the stage that owns them.
    assert "TOTAL_ARITHMETIC_MISMATCH" in codes          # consistency rules
    assert "PDF_TEXT_FONT_MIX_IN_LINE" in codes          # typography forensics
    assert "PDF_CONTENT_ANNOTATIONS" in codes            # PDF structure
    assert "PDF_IMAGE_EDITOR_PRODUCER" in codes          # metadata provenance
    assert any(code.startswith("TAMPER_") for code in codes)   # correlation layer
    assert document.risk_band == "high_concern"

    tampering = [f for f in findings_store.collect(db, document_id) if f.kind == "tampering"]
    assert tampering
    region = tampering[0]
    assert region.page == 1
    assert region.region and region.region["width"] > 0
    assert region.evidence["distinct_detectors"] >= 1
    # The region is named against an extracted field, not left anonymous.
    assert any(f.as_dict().get("affected_field") for f in tampering)


def test_findings_carry_the_full_evidence_contract(client, claims_token, db, tampered_invoice_pdf,
                                                   make_claim):
    data, mime = tampered_invoice_pdf
    claim = make_claim()
    document_id = _ingest(client, claims_token, data, "evidence.pdf", mime, claim["id"])
    run_analysis(db, document_id)
    db.commit()

    for finding in findings_store.collect(db, document_id):
        payload = finding.as_dict()
        for key in ("finding_id", "category", "severity", "confidence", "description",
                    "evidence", "detector", "model_version", "created_at", "provenance"):
            assert key in payload, key
        assert 0.0 <= payload["confidence"] <= 1.0
        assert payload["severity"] in ("info", "low", "medium", "high", "critical")
        assert payload["detector"] and payload["model_version"]


def test_ocr_failure_degrades_the_stage_and_preserves_the_document(
    client, claims_token, db, invoice_pdf, make_claim, monkeypatch
):
    data, mime = invoice_pdf
    claim = make_claim()
    document_id = _ingest(client, claims_token, data, "ocr-down.pdf", mime, claim["id"])

    def unavailable(*args, **kwargs):
        raise ProviderUnavailable("ocr", "OCR engine unavailable in this test")

    monkeypatch.setattr("app.services.pipeline.get_ocr_provider", unavailable)
    run = run_analysis(db, document_id)
    db.commit()

    statuses = {stage["key"]: stage["status"] for stage in run.stages}
    assert statuses["ocr"] == "unavailable"
    document = db.get(Document, document_id)
    assert document.processing_status in ("failed", "partial")
    assert "preserved" in document.processing_message
    # The evidence survives a provider outage.
    assert get_storage().exists("originals", document.storage_key)
    assert db.get(Document, document_id).sha256


def test_aigc_provider_failure_only_degrades_its_own_stage(
    client, claims_token, db, invoice_pdf, make_claim, monkeypatch
):
    data, mime = invoice_pdf
    claim = make_claim()
    document_id = _ingest(client, claims_token, data, "aigc-down.pdf", mime, claim["id"])

    def unavailable(*args, **kwargs):
        raise ProviderUnavailable("aigc", "detector offline")

    monkeypatch.setattr("app.services.pipeline.get_aigc_provider", unavailable)
    run = run_analysis(db, document_id)
    db.commit()

    statuses = {stage["key"]: stage["status"] for stage in run.stages}
    assert statuses["aigc"] == "unavailable"
    assert statuses["ocr"] == "completed"
    assert statuses["risk"] == "completed"
    document = db.get(Document, document_id)
    assert document.processing_status == "partial"
    assessment = db.execute(
        select(RiskAssessment).where(RiskAssessment.document_id == document_id)
    ).scalars().first()
    assert "AI-generated content analysis" in assessment.coverage["degraded_stages"]
    assert "partial coverage" in assessment.explanation


def test_reanalysis_preserves_human_review_decisions(
    client, claims_token, db, tampered_invoice_pdf, make_claim
):
    data, mime = tampered_invoice_pdf
    claim = make_claim()
    document_id = _ingest(client, claims_token, data, "reprocess.pdf", mime, claim["id"])
    run_analysis(db, document_id)
    db.commit()

    findings = findings_store.collect(db, document_id)
    target = next(f for f in findings if f.kind == "consistency")
    kind, row = findings_store.locate_finding(db, target.finding_id)
    row.status = "dismissed"
    row.review_reason = "Confirmed with the issuer that the printed total is correct."
    db.commit()

    run_analysis(db, document_id)
    db.commit()

    after = findings_store.collect(db, document_id)
    carried = [f for f in after if f.code == target.code]
    assert carried, "the equivalent finding should be regenerated"
    assert carried[0].status == "dismissed"
    assert carried[0].review_reason.startswith("Confirmed with the issuer")


def test_page_renders_and_forensic_layers_are_stored(client, claims_token, db, invoice_pdf,
                                                     make_claim):
    data, mime = invoice_pdf
    claim = make_claim()
    document_id = _ingest(client, claims_token, data, "layers.pdf", mime, claim["id"])
    run_analysis(db, document_id)
    db.commit()

    pages = db.execute(
        select(DocumentPage).where(DocumentPage.document_id == document_id)
    ).scalars().all()
    assert pages
    storage = get_storage()
    for page in pages:
        assert storage.exists("artifacts", page.render_key)
        assert page.artifacts.get("thumbnail")


def test_vector_pdf_skips_inapplicable_pixel_metrics(client, claims_token, db, invoice_pdf,
                                                     make_claim):
    """A vector page render has no compression history - saying so beats guessing."""
    data, mime = invoice_pdf
    claim = make_claim()
    document_id = _ingest(client, claims_token, data, "vector.pdf", mime, claim["id"])
    run = run_analysis(db, document_id)
    db.commit()

    forensics = next(s for s in run.stages if s["key"] == "forensics")
    raster = forensics["detail"].get("raster", {})
    assert raster.get("status") == "not_applicable"
    assert "vector" in raster["reason"]


def test_analysis_run_records_versions_and_provider_snapshot(client, claims_token, db,
                                                             invoice_pdf, make_claim):
    data, mime = invoice_pdf
    claim = make_claim()
    document_id = _ingest(client, claims_token, data, "versions.pdf", mime, claim["id"])
    run = run_analysis(db, document_id)
    db.commit()

    stored = db.get(AnalysisRun, run.id)
    assert stored.pipeline_version and stored.rules_version
    assert stored.provider_snapshot["ocr"]["key"]
    assert stored.provider_snapshot["storage"]
    assert stored.duration_ms >= 0
