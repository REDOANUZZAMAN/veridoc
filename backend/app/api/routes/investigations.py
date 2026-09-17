from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import investigation_payload, user_ref
from app.core.deps import DbSession, RequestContext, require
from app.core.errors import NotFoundError, ValidationFailure
from app.core.rbac import Perm
from app.db.enums import AuditAction, ClaimStatus, InvestigationStatus
from app.db.models.claim import Claim
from app.db.models.document import Document
from app.db.models.investigation import Investigation, InvestigationNote
from app.db.models.user import User
from app.schemas.common import Page, page_meta
from app.schemas.core import InvestigationCreate, InvestigationUpdate, NoteCreate
from app.services import audit, findings_store

router = APIRouter(prefix="/investigations", tags=["investigations"])


def _load(db: Session, investigation_id: str) -> Investigation:
    row = db.execute(
        select(Investigation).where(or_(Investigation.id == investigation_id,
                                        Investigation.case_number == investigation_id))
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"No investigation matching '{investigation_id}'.")
    return row


@router.get("", response_model=Page[dict], summary="List investigations")
def list_investigations(
    db: DbSession, user: Annotated[User, Depends(require(Perm.INVESTIGATION_READ))],
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    priority: str | None = None, assigned_to: str | None = None, mine: bool = False,
):
    query = select(Investigation)
    if status_filter:
        query = query.where(Investigation.status == status_filter)
    if priority:
        query = query.where(Investigation.priority == priority)
    if mine:
        query = query.where(Investigation.assigned_to_id == user.id)
    elif assigned_to:
        query = query.where(Investigation.assigned_to_id == assigned_to)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(Investigation.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    items = []
    for row in rows:
        payload = investigation_payload(row)
        claim = db.get(Claim, row.claim_id) if row.claim_id else None
        doc = db.get(Document, row.document_id) if row.document_id else None
        payload["claim_number"] = claim.claim_number if claim else None
        payload["customer_name"] = claim.customer_name if claim else None
        payload["risk_score"] = claim.risk_score if claim else None
        payload["risk_band"] = claim.risk_band if claim else None
        payload["document_ref"] = doc.document_ref if doc else None
        payload["document_type"] = doc.classification_type if doc else None
        items.append(payload)
    return Page[dict](items=items, meta=page_meta(int(total), page, page_size))


@router.post("", status_code=status.HTTP_201_CREATED, summary="Open an investigation")
def create_investigation(
    payload: InvestigationCreate, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.INVESTIGATION_ESCALATE))],
):
    claim = db.get(Claim, payload.claim_id)
    if claim is None:
        raise NotFoundError("The claim does not exist.")
    case_number = (f"INV-{datetime.now(timezone.utc).year}-"
                   f"{claim.claim_number[-6:]}-{int(datetime.now().timestamp()) % 1000:03d}")
    inv = Investigation(
        case_number=case_number, claim_id=claim.id, document_id=payload.document_id,
        title=payload.title, status=InvestigationStatus.OPEN, priority=payload.priority,
        assigned_to_id=payload.assigned_to_id, opened_by_id=user.id,
        opened_at=datetime.now(timezone.utc), risk_score_at_open=claim.risk_score,
        summary=payload.summary, context={"opened_by": "manual"},
    )
    db.add(inv)
    if claim.status not in {ClaimStatus.RESOLVED}:
        claim.status = ClaimStatus.INVESTIGATION
    db.flush()
    audit.record(
        db, action=AuditAction.INVESTIGATION_CREATED, resource_type="investigation",
        resource_id=inv.id, actor=user,
        summary=f"Investigation {case_number} opened on {claim.claim_number}.",
        after={"case_number": case_number, "priority": inv.priority,
               "assigned_to": payload.assigned_to_id}, **ctx,
    )
    db.commit()
    db.refresh(inv)
    return investigation_payload(inv, with_notes=True)


@router.get("/{investigation_id}", summary="Investigation detail with notes")
def get_investigation(
    investigation_id: str, db: DbSession,
    user: Annotated[User, Depends(require(Perm.INVESTIGATION_READ))],
):
    inv = _load(db, investigation_id)
    payload = investigation_payload(inv, with_notes=True)
    claim = db.get(Claim, inv.claim_id) if inv.claim_id else None
    if claim:
        payload["claim"] = {
            "id": claim.id, "claim_number": claim.claim_number,
            "customer_name": claim.customer_name, "policy_number": claim.policy_number,
            "status": claim.status, "risk_score": claim.risk_score,
            "risk_band": claim.risk_band, "claimed_amount": claim.claimed_amount,
            "currency": claim.currency,
        }
        findings = findings_store.collect_for_claim(db, claim.id)
        payload["findings"] = [f.as_dict() for f in findings[:30]]
        payload["documents"] = [
            {"id": d.id, "document_ref": d.document_ref,
             "classification_type": d.classification_type, "risk_score": d.risk_score,
             "risk_band": d.risk_band, "verification_state": d.verification_state}
            for d in db.execute(
                select(Document).where(Document.claim_id == claim.id,
                                       Document.deleted_at.is_(None))
            ).scalars().all()
        ]
    return payload


@router.patch("/{investigation_id}", summary="Update an investigation")
def update_investigation(
    investigation_id: str, payload: InvestigationUpdate, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.INVESTIGATION_NOTE))],
):
    inv = _load(db, investigation_id)
    data = payload.model_dump(exclude_unset=True)
    if "assigned_to_id" in data:
        require(Perm.INVESTIGATION_ASSIGN)(user)
    if data.get("status") == InvestigationStatus.CLOSED:
        require(Perm.INVESTIGATION_CLOSE)(user)
        if not (data.get("resolution_reason") or inv.resolution_reason):
            raise ValidationFailure("Closing an investigation requires a resolution reason.")
        inv.closed_at = datetime.now(timezone.utc)
    before = {k: getattr(inv, k) for k in data}
    for key, value in data.items():
        setattr(inv, key, value)
    audit.record(
        db, action=AuditAction.INVESTIGATION_UPDATED, resource_type="investigation",
        resource_id=inv.id, actor=user,
        summary=f"Investigation {inv.case_number} updated ({', '.join(data)}).",
        before={k: str(v) for k, v in before.items()},
        after={k: str(v) for k, v in data.items()}, **ctx,
    )
    db.commit()
    db.refresh(inv)
    return investigation_payload(inv, with_notes=True)


@router.post("/{investigation_id}/notes", status_code=status.HTTP_201_CREATED,
             summary="Add an investigation note")
def add_note(
    investigation_id: str, payload: NoteCreate, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.INVESTIGATION_NOTE))],
):
    inv = _load(db, investigation_id)
    note = InvestigationNote(
        investigation_id=inv.id, author_id=user.id, body=payload.body.strip(),
        note_type=payload.note_type, is_internal=payload.is_internal,
    )
    db.add(note)
    if inv.status == InvestigationStatus.OPEN:
        inv.status = InvestigationStatus.IN_PROGRESS
    db.flush()
    audit.record(
        db, action=AuditAction.INVESTIGATION_NOTE_ADDED, resource_type="investigation",
        resource_id=inv.id, actor=user,
        summary=f"Note added to {inv.case_number} by {user.email}.",
        metadata={"note_type": payload.note_type, "length": len(payload.body)}, **ctx,
    )
    db.commit()
    db.refresh(note)
    return {
        "id": note.id, "body": note.body, "note_type": note.note_type,
        "is_internal": note.is_internal, "author": user_ref(user),
        "created_at": note.created_at,
    }
