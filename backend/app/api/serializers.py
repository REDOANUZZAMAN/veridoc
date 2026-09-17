"""ORM -> API dictionaries.

Kept in one place so the investigation page, the claim page and the PDF report
all describe a document identically.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import DOCUMENT_TYPE_LABELS, RISK_BAND_LABELS
from app.db.models.analysis import AnalysisRun, RiskAssessment
from app.db.models.claim import Claim
from app.db.models.document import (
    Document,
    DocumentMetadataEntry,
    DocumentPage,
    ExtractedField,
    OcrResult,
)
from app.db.models.investigation import Investigation, ReviewActionRecord
from app.db.models.verification import VerificationRequest
from app.services import findings_store
from app.services.extract.schema import schema_for


def user_ref(user) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email,
        "role_name": user.role_name, "initials": user.initials,
    }


def finding_counts(db: Session, document_id: str) -> dict:
    findings = findings_store.collect(db, document_id)
    counts: dict[str, Any] = {
        "total": len(findings),
        "open": sum(1 for f in findings if f.status == "open"),
        "confirmed": sum(1 for f in findings if f.status == "confirmed"),
        "dismissed": sum(1 for f in findings if f.status == "dismissed"),
        "by_severity": {},
        "by_kind": {},
    }
    for f in findings:
        counts["by_severity"][f.severity] = counts["by_severity"].get(f.severity, 0) + 1
        counts["by_kind"][f.kind] = counts["by_kind"].get(f.kind, 0) + 1
    return counts


def document_summary(db: Session, doc: Document, *, with_counts: bool = True) -> dict:
    return {
        "id": doc.id,
        "document_ref": doc.document_ref,
        "claim_id": doc.claim_id,
        "claim_number": doc.claim.claim_number if doc.claim else None,
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "file_extension": doc.file_extension,
        "file_size": doc.file_size,
        "sha256": doc.sha256,
        "page_count": doc.page_count,
        "source": doc.source,
        "processing_status": doc.processing_status,
        "processing_message": doc.processing_message,
        "malware_status": doc.malware_status,
        "classification_type": doc.classification_type,
        "classification_label": DOCUMENT_TYPE_LABELS.get(doc.classification_type or "", None),
        "classification_confidence": doc.classification_confidence,
        "risk_score": doc.risk_score,
        "risk_band": doc.risk_band,
        "risk_band_label": RISK_BAND_LABELS.get(doc.risk_band or "", None),
        "verification_state": doc.verification_state,
        "uploaded_at": doc.uploaded_at,
        "uploaded_by": user_ref(doc.uploaded_by),
        "finding_counts": finding_counts(db, doc.id) if with_counts else {},
    }


def page_payload(page: DocumentPage) -> dict:
    return {
        "page_number": page.page_number,
        "width": page.width,
        "height": page.height,
        "render_dpi": page.render_dpi,
        "has_text_layer": page.has_text_layer,
        "text_char_count": page.text_char_count,
        "layers": sorted((page.artifacts or {}).keys()),
    }


def verification_payload(request: VerificationRequest) -> dict:
    result = request.result
    return {
        "id": request.id,
        "request_type": request.request_type,
        "provider_key": request.provider_key,
        "provider_label": request.provider_label,
        "provider_mode": request.provider_mode,
        "is_demo_provider": request.provider_mode == "demo",
        "status": request.status,
        "trigger": request.trigger,
        "requested_at": request.created_at,
        "request_payload": request.request_payload,
        "result": None if result is None else {
            "outcome": result.outcome,
            "summary": result.summary,
            "checks": result.checks,
            "latency_ms": result.latency_ms,
            "reference_id": result.reference_id,
            "is_demo_data": result.is_demo_data,
            "data_source_disclaimer": result.data_source_disclaimer,
            "error": result.error,
            "completed_at": result.created_at,
        },
    }


def run_payload(run: AnalysisRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "queue_mode": run.queue_mode,
        "queue_job_id": run.queue_job_id,
        "pipeline_version": run.pipeline_version,
        "rules_version": run.rules_version,
        "stages": run.stages,
        "provider_snapshot": run.provider_snapshot,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_ms": run.duration_ms,
        "findings_count": run.findings_count,
        "error": run.error,
        "triggered_by": user_ref(getattr(run, "triggered_by", None)),
        "created_at": run.created_at,
    }


def risk_payload(assessment: RiskAssessment | None) -> dict | None:
    if assessment is None:
        return None
    return {
        "id": assessment.id,
        "score": assessment.score,
        "band": assessment.band,
        "band_label": RISK_BAND_LABELS.get(assessment.band, assessment.band),
        "weights_version": assessment.weights_version,
        "signals": assessment.signals,
        "category_scores": assessment.category_scores,
        "top_reasons": assessment.top_reasons,
        "explanation": assessment.explanation,
        "interpretation_note": assessment.interpretation_note,
        "coverage": assessment.coverage,
        "created_at": assessment.created_at,
    }


def document_detail(db: Session, doc: Document) -> dict:
    base = document_summary(db, doc)
    pages = db.execute(
        select(DocumentPage).where(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number)
    ).scalars().all()
    ocr_rows = db.execute(
        select(OcrResult).where(OcrResult.document_id == doc.id)
        .order_by(OcrResult.page_number)
    ).scalars().all()
    fields = db.execute(
        select(ExtractedField).where(ExtractedField.document_id == doc.id)
        .order_by(ExtractedField.group_name, ExtractedField.field_key)
    ).scalars().all()
    metadata_rows = db.execute(
        select(DocumentMetadataEntry).where(DocumentMetadataEntry.document_id == doc.id)
        .order_by(DocumentMetadataEntry.group_name, DocumentMetadataEntry.key)
    ).scalars().all()
    latest_run = db.execute(
        select(AnalysisRun).where(AnalysisRun.document_id == doc.id)
        .order_by(AnalysisRun.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    assessment = db.execute(
        select(RiskAssessment).where(RiskAssessment.document_id == doc.id,
                                     RiskAssessment.is_superseded.is_(False))
        .order_by(RiskAssessment.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    verifications = db.execute(
        select(VerificationRequest).where(VerificationRequest.document_id == doc.id)
        .order_by(VerificationRequest.created_at.desc())
    ).scalars().all()
    reviews = db.execute(
        select(ReviewActionRecord).where(ReviewActionRecord.document_id == doc.id)
        .order_by(ReviewActionRecord.created_at.desc())
    ).scalars().all()

    schema = schema_for(doc.classification_type)
    return {
        **base,
        "artifact_prefix": doc.artifact_prefix,
        "verified_by": user_ref(getattr(doc, "verified_by", None)),
        "verification_note": doc.verification_note,
        "retention_expires_at": doc.retention_expires_at,
        "malware_detail": doc.malware_detail,
        "classification_detail": doc.classification_detail,
        "pages": [page_payload(p) for p in pages],
        "ocr": [
            {
                "page_number": r.page_number, "provider": r.provider,
                "provider_version": r.provider_version, "status": r.status, "error": r.error,
                "mean_confidence": r.mean_confidence, "word_count": r.word_count,
                "duration_ms": r.duration_ms, "raw_text": r.raw_text,
                "words": r.words,
            }
            for r in ocr_rows
        ],
        "extracted_fields": [
            {
                "field_key": f.field_key, "field_label": f.field_label,
                "value_raw": f.value_raw, "value": f.value_normalized,
                "value_type": f.value_type, "confidence": f.confidence, "page": f.page,
                "bbox": f.bbox, "source": f.source, "required": f.is_required,
                "group": f.group_name,
            }
            for f in fields if f.group_name != "line_items"
        ],
        "line_items": [
            {
                "field_key": f.field_key, "label": f.field_label, "raw": f.value_raw,
                "value": f.value_normalized, "page": f.page, "bbox": f.bbox,
            }
            for f in fields if f.group_name == "line_items"
        ],
        "metadata_entries": [
            {
                "group": m.group_name, "key": m.key, "value": m.value,
                "is_anomalous": m.is_anomalous, "note": m.note,
            }
            for m in metadata_rows
        ],
        "findings": [f.as_dict() for f in findings_store.collect(db, doc.id)],
        "risk_assessment": risk_payload(assessment),
        "latest_run": run_payload(latest_run),
        "verification": [verification_payload(v) for v in verifications],
        "review_actions": [
            {
                "id": r.id, "action": r.action, "reason": r.reason,
                "finding_id": r.finding_id, "finding_kind": r.finding_kind,
                "previous_status": r.previous_status, "new_status": r.new_status,
                "actor": user_ref(r.actor), "actor_role": r.actor_role,
                "created_at": r.created_at, "context": r.context,
            }
            for r in reviews
        ],
        "schema_fields": [
            {"key": f.key, "label": f.label, "type": f.value_type, "required": f.required,
             "group": f.group, "sensitive": f.sensitive}
            for f in schema.fields
        ],
        "schema_label": schema.label,
    }


def claim_summary(db: Session, claim: Claim) -> dict:
    doc_count = db.execute(
        select(func.count()).select_from(Document).where(
            Document.claim_id == claim.id, Document.deleted_at.is_(None))
    ).scalar_one()
    findings = findings_store.collect_for_claim(db, claim.id)
    return {
        "id": claim.id,
        "claim_number": claim.claim_number,
        "customer_name": claim.customer_name,
        "policy_number": claim.policy_number,
        "insurer": claim.insurer,
        "claim_type": claim.claim_type,
        "status": claim.status,
        "currency": claim.currency,
        "claimed_amount": claim.claimed_amount,
        "risk_score": claim.risk_score,
        "risk_band": claim.risk_band,
        "risk_band_label": RISK_BAND_LABELS.get(claim.risk_band or "", None),
        "incident_date": claim.incident_date,
        "document_count": int(doc_count),
        "open_findings": sum(1 for f in findings if f.status == "open"),
        "assigned_investigator": user_ref(claim.assigned_investigator),
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
    }


def investigation_payload(inv: Investigation, *, with_notes: bool = False) -> dict:
    payload = {
        "id": inv.id,
        "case_number": inv.case_number,
        "claim_id": inv.claim_id,
        "document_id": inv.document_id,
        "title": inv.title,
        "status": inv.status,
        "priority": inv.priority,
        "assigned_to": user_ref(inv.assigned_to),
        "opened_by": user_ref(inv.opened_by),
        "opened_at": inv.opened_at,
        "closed_at": inv.closed_at,
        "resolution": inv.resolution,
        "resolution_reason": inv.resolution_reason,
        "summary": inv.summary,
        "risk_score_at_open": inv.risk_score_at_open,
        "context": inv.context,
        "note_count": len(inv.notes or []),
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
    }
    if with_notes:
        payload["notes"] = [
            {
                "id": n.id, "body": n.body, "note_type": n.note_type,
                "is_internal": n.is_internal, "author": user_ref(n.author),
                "created_at": n.created_at,
            }
            for n in sorted(inv.notes or [], key=lambda x: x.created_at)
        ]
    return payload
