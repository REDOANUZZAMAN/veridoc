from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select

from app.api.serializers import (
    claim_summary,
    document_detail,
    user_ref,
)
from app.core.config import PIPELINE_VERSION, RULES_VERSION
from app.core.deps import DbSession, RequestContext, require
from app.core.errors import NotFoundError, ValidationFailure
from app.core.rbac import ROLE_LABELS, Perm
from app.core.security import sha256_bytes
from app.db.enums import AuditAction
from app.db.models.audit import AuditLog
from app.db.models.claim import Claim
from app.db.models.document import Document
from app.db.models.report import Report
from app.db.models.user import User
from app.schemas.common import Page, page_meta
from app.schemas.core import ReportCreate, ReportOut
from app.services import audit
from app.services.aigc.base import BAND_LABELS
from app.services.reports.pdf_report import build_report
from app.services.storage.factory import get_storage

router = APIRouter(prefix="/reports", tags=["reports"])


def _aigc_summary(findings: list[dict]) -> dict:
    aigc = [f for f in findings if f.get("kind") == "aigc"]
    if not aigc:
        return {}
    best = max(aigc, key=lambda f: (f.get("evidence") or {}).get("likelihood", 0))
    evidence = best.get("evidence") or {}
    provider_version = (best.get("model_version") or "@").split("@")
    return {
        "provider_label": best.get("provider_label"),
        "model_name": provider_version[0],
        "model_version": provider_version[-1],
        "is_demo": best.get("is_demo_provider", True),
        "max_likelihood": evidence.get("likelihood", 0),
        "band": best.get("likelihood_band"),
        "band_label": BAND_LABELS.get(best.get("likelihood_band", ""), "-"),
        "disclaimer": evidence.get("provider_disclaimer"),
    }


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED,
             summary="Generate an investigation report (PDF)")
def generate_report(
    payload: ReportCreate, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.REPORT_GENERATE))],
):
    if not payload.document_id and not payload.claim_id:
        raise ValidationFailure("Supply document_id or claim_id.")

    document = None
    claim = None
    detail: dict = {}
    if payload.document_id:
        document = db.execute(
            select(Document).where(Document.id == payload.document_id,
                                   Document.deleted_at.is_(None))
        ).scalar_one_or_none()
        if document is None:
            raise NotFoundError("The document does not exist.")
        detail = document_detail(db, document)
        claim = document.claim
    if payload.claim_id and claim is None:
        claim = db.execute(
            select(Claim).where(Claim.id == payload.claim_id, Claim.deleted_at.is_(None))
        ).scalar_one_or_none()
        if claim is None:
            raise NotFoundError("The claim does not exist.")

    count = db.execute(select(func.count()).select_from(Report)).scalar_one()
    report_ref = f"RPT-{datetime.now(timezone.utc).year}-{count + 1:06d}"

    audit_rows = db.execute(
        select(AuditLog).where(
            AuditLog.resource_id == (document.id if document else claim.id)
        ).order_by(AuditLog.seq.desc()).limit(25)
    ).scalars().all()
    from app.services.audit import verify_chain

    report_payload = {
        "report_ref": report_ref,
        "title": payload.title or (
            f"Document investigation report — {document.document_ref}" if document
            else f"Claim investigation report — {claim.claim_number}"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": user.email,
        "generated_by_role": ROLE_LABELS.get(user.role_name, user.role_name),
        "document": detail,
        "claim": claim_summary(db, claim) if claim else {},
        "risk": detail.get("risk_assessment") or {},
        "run": detail.get("latest_run") or {},
        "findings": detail.get("findings") or [],
        "extracted_fields": detail.get("extracted_fields") or [],
        "line_items": detail.get("line_items") or [],
        "verification": detail.get("verification") or [],
        "review_actions": detail.get("review_actions") or [],
        "aigc_summary": _aigc_summary(detail.get("findings") or []),
        "audit": [
            {"seq": a.seq, "created_at": a.created_at, "actor_email": a.actor_email,
             "action": a.action, "summary": a.summary}
            for a in reversed(audit_rows)
        ],
        "audit_chain": verify_chain(db, limit=500),
        "notes": payload.notes,
    }
    pdf = build_report(report_payload)
    storage = get_storage()
    key = f"{report_ref}/{report_ref}.pdf"
    storage.write("reports", key, pdf, "application/pdf")

    report = Report(
        report_ref=report_ref,
        document_id=document.id if document else None,
        claim_id=claim.id if claim else None,
        investigation_id=payload.investigation_id,
        generated_by_id=user.id,
        report_type="document_investigation" if document else "claim_investigation",
        format="pdf", storage_key=key, file_size=len(pdf), sha256=sha256_bytes(pdf),
        document_sha256=document.sha256 if document else None,
        pipeline_version=(detail.get("latest_run") or {}).get("pipeline_version",
                                                              PIPELINE_VERSION),
        rules_version=(detail.get("latest_run") or {}).get("rules_version", RULES_VERSION),
        title=report_payload["title"], notes=payload.notes,
        # JSON-encoded so timestamps inside the risk snapshot round-trip through
        # JSONB rather than failing the insert.
        snapshot=jsonable_encoder({
            "risk": report_payload["risk"],
            "finding_count": len(report_payload["findings"]),
            "verification_outcomes": [
                (v.get("result") or {}).get("outcome") for v in report_payload["verification"]
            ],
            "generated_by": user.email,
        }),
    )
    db.add(report)
    db.flush()
    audit.record(
        db, action=AuditAction.REPORT_GENERATED, resource_type="report", resource_id=report.id,
        actor=user,
        summary=(f"{report_ref} generated for "
                 f"{document.document_ref if document else claim.claim_number}."),
        after={"report_ref": report_ref, "sha256": report.sha256, "bytes": len(pdf)},
        metadata={"document_sha256": report.document_sha256,
                  "findings": len(report_payload["findings"]),
                  "document_id": document.id if document else None,
                  "claim_id": claim.id if claim else None}, **ctx,
    )
    # Also recorded against the subject, so a document's own history shows that a
    # report was issued from it - that is the question an investigator asks of
    # the audit tab, and it should not require a join to answer.
    subject_id = document.id if document else (claim.id if claim else None)
    if subject_id:
        audit.record(
            db, action=AuditAction.REPORT_GENERATED,
            resource_type="document" if document else "claim", resource_id=subject_id,
            actor=user,
            summary=(f"Evidence report {report_ref} generated by {user.email} "
                     f"({len(report_payload['findings'])} findings, "
                     f"{len(pdf)} bytes)."),
            metadata={"report_ref": report_ref, "report_id": report.id,
                      "report_sha256": report.sha256}, **ctx,
        )
    db.commit()
    db.refresh(report)
    return ReportOut(**_report_payload(report))


def _report_payload(report: Report) -> dict:
    return {
        "id": report.id, "report_ref": report.report_ref, "report_type": report.report_type,
        "title": report.title, "format": report.format, "file_size": report.file_size,
        "sha256": report.sha256, "document_sha256": report.document_sha256,
        "document_id": report.document_id, "claim_id": report.claim_id,
        "pipeline_version": report.pipeline_version, "rules_version": report.rules_version,
        "generated_by": user_ref(report.generated_by), "created_at": report.created_at,
        "notes": report.notes,
    }


@router.get("", response_model=Page[ReportOut], summary="List generated reports")
def list_reports(
    db: DbSession, user: Annotated[User, Depends(require(Perm.REPORT_READ))],
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    document_id: str | None = None, claim_id: str | None = None,
):
    query = select(Report)
    if document_id:
        query = query.where(Report.document_id == document_id)
    if claim_id:
        query = query.where(Report.claim_id == claim_id)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(Report.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[ReportOut](items=[ReportOut(**_report_payload(r)) for r in rows],
                           meta=page_meta(int(total), page, page_size))


@router.get("/{report_id}", response_model=ReportOut, summary="Report metadata")
def get_report(report_id: str, db: DbSession,
               user: Annotated[User, Depends(require(Perm.REPORT_READ))]):
    report = db.get(Report, report_id)
    if report is None:
        raise NotFoundError("The report does not exist.")
    return ReportOut(**_report_payload(report))


@router.get("/{report_id}/export", summary="Download the report PDF")
def export_report(
    report_id: str, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.REPORT_READ))],
    disposition: str = Query("attachment", pattern="^(inline|attachment)$"),
):
    report = db.get(Report, report_id)
    if report is None or not report.storage_key:
        raise NotFoundError("The report file is not available.")
    data = get_storage().read("reports", report.storage_key)
    audit.record(
        db, action=AuditAction.REPORT_GENERATED, resource_type="report", resource_id=report.id,
        actor=user, summary=f"{user.email} downloaded {report.report_ref}.",
        metadata={"action": "download"}, **ctx,
    )
    db.commit()
    return Response(
        content=data, media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{report.report_ref}.pdf"',
            "X-Report-SHA256": report.sha256 or "",
            "Cache-Control": "private, no-store",
        },
    )
