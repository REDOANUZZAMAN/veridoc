from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import (
    claim_summary,
    document_summary,
    investigation_payload,
    user_ref,
    verification_payload,
)
from app.core.deps import DbSession, RequestContext, require
from app.core.errors import ConflictError, NotFoundError, ValidationFailure
from app.core.rbac import Perm
from app.db.enums import AuditAction, ClaimStatus, InvestigationStatus
from app.db.models.claim import Claim
from app.db.models.document import Document, ExtractedField
from app.db.models.investigation import Investigation, ReviewActionRecord
from app.db.models.user import User
from app.db.models.verification import VerificationRequest
from app.schemas.common import Page, page_meta
from app.schemas.core import (
    ClaimCreate,
    ClaimDecisionRequest,
    ClaimDetailOut,
    ClaimOut,
    ClaimUpdate,
)
from app.services import audit, findings_store
from app.services.crossdoc.engine import DocumentSnapshot, compare_documents

router = APIRouter(prefix="/claims", tags=["claims"])


def _load(db: Session, claim_id: str) -> Claim:
    claim = db.execute(
        select(Claim).where(Claim.id == claim_id, Claim.deleted_at.is_(None))
    ).scalar_one_or_none()
    if claim is None:
        claim = db.execute(
            select(Claim).where(Claim.claim_number == claim_id, Claim.deleted_at.is_(None))
        ).scalar_one_or_none()
    if claim is None:
        raise NotFoundError(f"No claim matching '{claim_id}'.")
    return claim


def _next_claim_number(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    count = db.execute(select(func.count()).select_from(Claim)).scalar_one()
    return f"CLM-{year}-{count + 1:06d}"


@router.post("", response_model=ClaimDetailOut, status_code=status.HTTP_201_CREATED,
             summary="Create a claim")
def create_claim(
    payload: ClaimCreate, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.CLAIM_CREATE))],
):
    number = payload.claim_number or _next_claim_number(db)
    if db.execute(select(Claim).where(Claim.claim_number == number)).scalar_one_or_none():
        raise ConflictError(f"Claim number {number} already exists.")
    claim = Claim(
        claim_number=number, customer_name=payload.customer_name.strip(),
        customer_dob=payload.customer_dob, customer_email=payload.customer_email,
        customer_phone=payload.customer_phone, policy_number=payload.policy_number.strip().upper(),
        insurer=payload.insurer, claim_type=payload.claim_type,
        incident_date=payload.incident_date, claimed_amount=payload.claimed_amount,
        currency=payload.currency, summary=payload.summary,
        status=ClaimStatus.SUBMITTED, submitted_at=datetime.now(timezone.utc),
        created_by_id=user.id,
    )
    db.add(claim)
    db.flush()
    audit.record(
        db, action=AuditAction.CLAIM_CREATED, resource_type="claim", resource_id=claim.id,
        actor=user, summary=f"Claim {number} created for policy {claim.policy_number}.",
        after={"claim_number": number, "policy_number": claim.policy_number,
               "claimed_amount": str(claim.claimed_amount) if claim.claimed_amount else None,
               "status": claim.status}, **ctx,
    )
    db.commit()
    db.refresh(claim)
    return _detail(db, claim)


@router.get("", response_model=Page[ClaimOut], summary="List claims")
def list_claims(
    db: DbSession, user: Annotated[User, Depends(require(Perm.CLAIM_READ))],
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    risk_band: str | None = None,
    assigned_to: str | None = None,
    search: str | None = Query(None, max_length=120),
    sort: str = Query("created_at", pattern="^(created_at|risk_score|claim_number)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    query = select(Claim).where(Claim.deleted_at.is_(None))
    if status_filter:
        query = query.where(Claim.status == status_filter)
    if risk_band:
        query = query.where(Claim.risk_band == risk_band)
    if assigned_to:
        query = query.where(Claim.assigned_investigator_id == assigned_to)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(
            Claim.claim_number.ilike(like), Claim.customer_name.ilike(like),
            Claim.policy_number.ilike(like),
        ))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    column = {"created_at": Claim.created_at, "risk_score": Claim.risk_score,
              "claim_number": Claim.claim_number}[sort]
    query = query.order_by(column.desc() if order == "desc" else column.asc())
    rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return Page[ClaimOut](
        items=[ClaimOut(**claim_summary(db, c)) for c in rows],
        meta=page_meta(int(total), page, page_size),
    )


def _detail(db: Session, claim: Claim) -> ClaimDetailOut:
    docs = db.execute(
        select(Document).where(Document.claim_id == claim.id, Document.deleted_at.is_(None))
        .order_by(Document.uploaded_at.asc())
    ).scalars().all()
    findings = findings_store.collect_for_claim(db, claim.id)
    verifications = db.execute(
        select(VerificationRequest).where(VerificationRequest.claim_id == claim.id)
        .order_by(VerificationRequest.created_at.desc())
    ).scalars().all()
    investigations = db.execute(
        select(Investigation).where(Investigation.claim_id == claim.id)
        .order_by(Investigation.created_at.desc())
    ).scalars().all()
    reviews = db.execute(
        select(ReviewActionRecord).where(ReviewActionRecord.claim_id == claim.id)
        .order_by(ReviewActionRecord.created_at.desc()).limit(50)
    ).scalars().all()

    by_severity: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_kind[f.kind] = by_kind.get(f.kind, 0) + 1

    snapshots = []
    for doc in docs:
        rows = db.execute(
            select(ExtractedField).where(ExtractedField.document_id == doc.id)
        ).scalars().all()
        fields = {}
        for row in rows:
            if row.group_name == "line_items":
                continue
            current = fields.get(row.field_key)
            if current and current["confidence"] >= row.confidence:
                continue
            fields[row.field_key] = {"value": row.value_normalized, "raw": row.value_raw,
                                      "confidence": row.confidence, "page": row.page,
                                      "bbox": row.bbox}
        if fields:
            from app.db.enums import DOCUMENT_TYPE_LABELS

            snapshots.append(DocumentSnapshot(
                document_id=doc.id, document_ref=doc.document_ref,
                document_type=doc.classification_type or "other",
                label=DOCUMENT_TYPE_LABELS.get(doc.classification_type or "other", "Document"),
                fields=fields,
            ))
    cross = compare_documents(snapshots, claim={
        "claim_number": claim.claim_number, "policy_number": claim.policy_number,
        "customer_name": claim.customer_name,
        "customer_dob": claim.customer_dob.isoformat() if claim.customer_dob else None,
        "claimed_amount": str(claim.claimed_amount) if claim.claimed_amount else None,
        "incident_date": claim.incident_date.isoformat() if claim.incident_date else None,
    }).summary() if snapshots else {}

    timeline = [
        {"at": claim.created_at, "type": "claim_created",
         "summary": f"Claim {claim.claim_number} created", "actor": user_ref(claim.created_by)},
        *[{"at": d.uploaded_at, "type": "document_uploaded",
           "summary": f"{d.document_ref} uploaded ({d.original_filename})",
           "actor": user_ref(d.uploaded_by)} for d in docs],
        *[{"at": r.created_at, "type": "review_action",
           "summary": f"{r.action} - {(r.reason or '')[:120]}", "actor": user_ref(r.actor)}
          for r in reviews],
        *[{"at": i.created_at, "type": "investigation",
           "summary": f"{i.case_number}: {i.title} ({i.status})",
           "actor": user_ref(i.opened_by)} for i in investigations],
    ]
    if claim.decided_at:
        timeline.append({"at": claim.decided_at, "type": "claim_decision",
                         "summary": f"Decision recorded: {claim.decision}", "actor": None})
    timeline.sort(key=lambda e: e["at"] or datetime.min.replace(tzinfo=timezone.utc))

    return ClaimDetailOut(
        **claim_summary(db, claim),
        customer_dob=claim.customer_dob, customer_email=claim.customer_email,
        customer_phone=claim.customer_phone, summary=claim.summary, decision=claim.decision,
        decision_reason=claim.decision_reason, decided_at=claim.decided_at,
        created_by=user_ref(claim.created_by),
        documents=[document_summary(db, d) for d in docs],
        verification=[verification_payload(v) for v in verifications],
        findings_summary={
            "total": len(findings), "by_severity": by_severity, "by_kind": by_kind,
            "open": sum(1 for f in findings if f.status == "open"),
            "confirmed": sum(1 for f in findings if f.status == "confirmed"),
            "dismissed": sum(1 for f in findings if f.status == "dismissed"),
            "top": [f.as_dict() for f in findings[:8]],
        },
        investigations=[investigation_payload(i) for i in investigations],
        cross_document=cross,
        timeline=timeline,
    )


@router.get("/{claim_id}", response_model=ClaimDetailOut, summary="Claim detail")
def get_claim(claim_id: str, db: DbSession,
              user: Annotated[User, Depends(require(Perm.CLAIM_READ))]):
    return _detail(db, _load(db, claim_id))


@router.patch("/{claim_id}", response_model=ClaimDetailOut, summary="Update a claim")
def update_claim(
    claim_id: str, payload: ClaimUpdate, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.CLAIM_UPDATE))],
):
    claim = _load(db, claim_id)
    before = {k: getattr(claim, k) for k in payload.model_dump(exclude_unset=True)}
    data = payload.model_dump(exclude_unset=True)
    if "assigned_investigator_id" in data and data["assigned_investigator_id"]:
        require(Perm.INVESTIGATION_ASSIGN)(user)
        if db.get(User, data["assigned_investigator_id"]) is None:
            raise ValidationFailure("The assigned investigator does not exist.")
    for key, value in data.items():
        setattr(claim, key, value)
    if "currency" in data and data["currency"]:
        claim.currency = data["currency"].upper()
    audit.record(
        db, action=AuditAction.CLAIM_STATUS_CHANGED if "status" in data else AuditAction.CLAIM_CREATED,
        resource_type="claim", resource_id=claim.id, actor=user,
        summary=f"Claim {claim.claim_number} updated ({', '.join(data)}).",
        before={k: str(v) for k, v in before.items()},
        after={k: str(v) for k, v in data.items()}, **ctx,
    )
    db.commit()
    db.refresh(claim)
    return _detail(db, claim)


@router.post("/{claim_id}/decision", response_model=ClaimDetailOut,
             summary="Record the final human decision on a claim")
def decide_claim(
    claim_id: str, payload: ClaimDecisionRequest, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.CLAIM_DECIDE))],
):
    claim = _load(db, claim_id)
    open_high = [
        f for f in findings_store.collect_for_claim(db, claim.id)
        if f.severity in {"high", "critical"} and f.status == "open"
    ]
    if payload.decision == "approve" and open_high:
        raise ConflictError(
            f"{len(open_high)} high or critical finding(s) are still unreviewed. Confirm or "
            "dismiss each one (with a reason) before approving - automated findings must not "
            "become a claim decision by default."
        )
    before = {"status": claim.status, "decision": claim.decision}
    claim.decision = payload.decision
    claim.decision_reason = payload.reason
    claim.decided_at = datetime.now(timezone.utc)
    claim.decided_by_id = user.id
    claim.status = ClaimStatus.RESOLVED
    if payload.close_investigations:
        for inv in db.execute(
            select(Investigation).where(Investigation.claim_id == claim.id,
                                        Investigation.status != InvestigationStatus.CLOSED)
        ).scalars().all():
            inv.status = InvestigationStatus.CLOSED
            inv.closed_at = datetime.now(timezone.utc)
            inv.resolution = payload.decision
            inv.resolution_reason = payload.reason
    audit.record(
        db, action=AuditAction.CLAIM_DECISION, resource_type="claim", resource_id=claim.id,
        actor=user,
        summary=f"Claim {claim.claim_number} decision '{payload.decision}' recorded by {user.email}.",
        before=before,
        after={"status": claim.status, "decision": claim.decision,
               "decided_by": user.email},
        metadata={"reason": payload.reason[:400],
                  "risk_score_at_decision": claim.risk_score,
                  "unreviewed_high_findings": len(open_high)}, **ctx,
    )
    db.commit()
    db.refresh(claim)
    return _detail(db, claim)
