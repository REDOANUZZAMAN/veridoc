from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select

from app.api.serializers import user_ref
from app.core.deps import DbSession, require
from app.core.rbac import Perm
from app.db.enums import (
    DOCUMENT_TYPE_LABELS,
    RISK_BAND_LABELS,
    ClaimStatus,
    InvestigationStatus,
    ProcessingStatus,
    RiskBand,
    VerificationState,
)
from app.db.models.analysis import AnalysisRun
from app.db.models.claim import Claim
from app.db.models.document import Document
from app.db.models.findings import (
    AigcFinding,
    ConsistencyFinding,
    CrossDocumentFinding,
    ForensicFinding,
    TamperingFinding,
)
from app.db.models.investigation import Investigation
from app.db.models.user import User
from app.db.models.verification import VerificationRequest, VerificationResult

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

FINDING_MODELS = {
    "forensic": ForensicFinding, "aigc": AigcFinding, "tampering": TamperingFinding,
    "consistency": ConsistencyFinding, "cross_document": CrossDocumentFinding,
}


@router.get("", summary="Operational dashboard metrics")
def dashboard(
    db: DbSession, user: Annotated[User, Depends(require(Perm.DASHBOARD_READ))],
    days: int = Query(14, ge=3, le=90),
):
    active_docs = Document.deleted_at.is_(None)

    status_rows = db.execute(
        select(Document.processing_status, func.count())
        .where(active_docs).group_by(Document.processing_status)
    ).all()
    status_counts = {row[0]: int(row[1]) for row in status_rows}

    band_rows = db.execute(
        select(Document.risk_band, func.count())
        .where(active_docs, Document.risk_band.is_not(None)).group_by(Document.risk_band)
    ).all()
    band_counts = {row[0]: int(row[1]) for row in band_rows}

    type_rows = db.execute(
        select(Document.classification_type, func.count())
        .where(active_docs, Document.classification_type.is_not(None))
        .group_by(Document.classification_type).order_by(func.count().desc())
    ).all()

    verification_state_rows = db.execute(
        select(Document.verification_state, func.count())
        .where(active_docs).group_by(Document.verification_state)
    ).all()
    verification_states = {row[0]: int(row[1]) for row in verification_state_rows}

    total_docs = int(db.execute(
        select(func.count()).select_from(Document).where(active_docs)
    ).scalar_one())
    processed = sum(status_counts.get(s, 0) for s in
                    (ProcessingStatus.ANALYZED, ProcessingStatus.PARTIAL))
    pending_review = int(db.execute(
        select(func.count()).select_from(Document).where(
            active_docs,
            Document.verification_state.in_([VerificationState.UNVERIFIED,
                                            VerificationState.IN_REVIEW]),
            Document.risk_band.in_([RiskBand.REVIEW_RECOMMENDED, RiskBand.HIGH_CONCERN]),
        )
    ).scalar_one())

    # --- findings by category ------------------------------------------------
    findings_by_kind: dict[str, dict] = {}
    for kind, model in FINDING_MODELS.items():
        rows = db.execute(
            select(model.severity, func.count()).group_by(model.severity)
        ).all()
        by_sev = {row[0]: int(row[1]) for row in rows}
        open_count = int(db.execute(
            select(func.count()).select_from(model).where(model.status == "open")
        ).scalar_one())
        findings_by_kind[kind] = {
            "total": sum(by_sev.values()), "open": open_count, "by_severity": by_sev,
        }

    top_finding_rows = db.execute(
        select(ConsistencyFinding.finding_code, func.count())
        .group_by(ConsistencyFinding.finding_code).order_by(func.count().desc()).limit(6)
    ).all()
    top_forensic_rows = db.execute(
        select(ForensicFinding.finding_code, func.count())
        .group_by(ForensicFinding.finding_code).order_by(func.count().desc()).limit(6)
    ).all()

    # --- daily volume --------------------------------------------------------
    since = datetime.now(timezone.utc) - timedelta(days=days)
    volume_rows = db.execute(
        select(
            func.date_trunc("day", Document.uploaded_at).label("day"),
            func.count(),
            func.sum(case((Document.risk_band == RiskBand.HIGH_CONCERN, 1), else_=0)),
            func.sum(case((Document.risk_band == RiskBand.REVIEW_RECOMMENDED, 1), else_=0)),
            func.sum(case((Document.risk_band == RiskBand.LOW_CONCERN, 1), else_=0)),
        )
        .where(active_docs, Document.uploaded_at >= since)
        .group_by("day").order_by("day")
    ).all()
    daily = [
        {"date": row[0].date().isoformat(), "documents": int(row[1]),
         "high_concern": int(row[2] or 0), "review_recommended": int(row[3] or 0),
         "low_concern": int(row[4] or 0)}
        for row in volume_rows
    ]

    # --- claims --------------------------------------------------------------
    claim_status_rows = db.execute(
        select(Claim.status, func.count()).where(Claim.deleted_at.is_(None))
        .group_by(Claim.status)
    ).all()
    claim_statuses = {row[0]: int(row[1]) for row in claim_status_rows}

    exposure = db.execute(
        select(func.coalesce(func.sum(Claim.claimed_amount), 0)).where(
            Claim.deleted_at.is_(None),
            Claim.risk_band.in_([RiskBand.REVIEW_RECOMMENDED, RiskBand.HIGH_CONCERN]),
            Claim.status != ClaimStatus.RESOLVED,
        )
    ).scalar_one()

    # --- verification --------------------------------------------------------
    verification_rows = db.execute(
        select(VerificationResult.outcome, func.count()).group_by(VerificationResult.outcome)
    ).all()
    verification_outcomes = {row[0]: int(row[1]) for row in verification_rows}
    demo_verification_count = int(db.execute(
        select(func.count()).select_from(VerificationRequest)
        .where(VerificationRequest.provider_mode == "demo")
    ).scalar_one())

    # --- recent investigations ----------------------------------------------
    investigations = db.execute(
        select(Investigation).order_by(Investigation.created_at.desc()).limit(10)
    ).scalars().all()
    recent = []
    for inv in investigations:
        claim = db.get(Claim, inv.claim_id) if inv.claim_id else None
        doc = db.get(Document, inv.document_id) if inv.document_id else None
        recent.append({
            "id": inv.id, "case_number": inv.case_number,
            "claim_id": inv.claim_id,
            "claim_number": claim.claim_number if claim else None,
            "customer_name": claim.customer_name if claim else None,
            "document_id": inv.document_id,
            "document_ref": doc.document_ref if doc else None,
            "document_type": DOCUMENT_TYPE_LABELS.get(
                (doc.classification_type if doc else "") or "", None),
            "risk_score": claim.risk_score if claim else inv.risk_score_at_open,
            "risk_band": claim.risk_band if claim else None,
            "status": inv.status, "priority": inv.priority,
            "assigned_to": user_ref(inv.assigned_to),
            "created_at": inv.created_at,
        })

    # --- pipeline health ----------------------------------------------------
    run_rows = db.execute(
        select(AnalysisRun.status, func.count(), func.avg(AnalysisRun.duration_ms))
        .group_by(AnalysisRun.status)
    ).all()
    runs = {row[0]: {"count": int(row[1]),
                     "avg_duration_ms": int(row[2] or 0)} for row in run_rows}

    queue_depth = int(db.execute(
        select(func.count()).select_from(Document).where(
            active_docs, Document.processing_status.in_([ProcessingStatus.QUEUED,
                                                        ProcessingStatus.PROCESSING]))
    ).scalar_one())

    return {
        "generated_at": datetime.now(timezone.utc),
        "cards": {
            "documents_total": total_docs,
            "documents_processed": processed,
            "pending_review": pending_review,
            "high_concern": band_counts.get(RiskBand.HIGH_CONCERN, 0),
            "verified": verification_states.get(VerificationState.VERIFIED, 0),
            "processing_errors": (status_counts.get(ProcessingStatus.FAILED, 0)
                                  + status_counts.get(ProcessingStatus.QUARANTINED, 0)),
            "in_flight": queue_depth,
            "open_investigations": int(db.execute(
                select(func.count()).select_from(Investigation)
                .where(Investigation.status != InvestigationStatus.CLOSED)
            ).scalar_one()),
            "flagged_exposure": float(exposure or 0),
        },
        "documents_by_status": [
            {"status": key, "count": value} for key, value in sorted(status_counts.items())
        ],
        "risk_distribution": [
            {"band": band, "label": RISK_BAND_LABELS.get(band, band),
             "count": band_counts.get(band, 0)}
            for band in (RiskBand.LOW_CONCERN, RiskBand.REVIEW_RECOMMENDED,
                         RiskBand.HIGH_CONCERN)
        ],
        "document_types": [
            {"type": row[0], "label": DOCUMENT_TYPE_LABELS.get(row[0], row[0]),
             "count": int(row[1])}
            for row in type_rows
        ],
        "findings_by_kind": findings_by_kind,
        "top_consistency_findings": [{"code": r[0], "count": int(r[1])}
                                     for r in top_finding_rows],
        "top_forensic_findings": [{"code": r[0], "count": int(r[1])}
                                  for r in top_forensic_rows],
        "daily_volume": daily,
        "claims_by_status": [{"status": k, "count": v} for k, v in sorted(claim_statuses.items())],
        "verification_outcomes": [{"outcome": k, "count": v}
                                  for k, v in sorted(verification_outcomes.items())],
        "verification_note": (
            f"{demo_verification_count} verification request(s) were answered by demo providers "
            "using the bundled sample registry."
        ),
        "verification_states": [{"state": k, "count": v}
                                for k, v in sorted(verification_states.items())],
        "recent_investigations": recent,
        "pipeline_runs": runs,
    }
