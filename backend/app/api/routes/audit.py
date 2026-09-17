from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core.deps import DbSession, require
from app.core.rbac import Perm
from app.db.enums import AuditAction
from app.db.models.audit import AuditLog
from app.db.models.user import User
from app.schemas.common import Page, page_meta
from app.schemas.core import AuditOut
from app.services.audit import verify_chain

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=Page[AuditOut], summary="Query the audit trail")
def list_audit(
    db: DbSession, user: Annotated[User, Depends(require(Perm.AUDIT_READ))],
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    action: str | None = None, resource_type: str | None = None,
    resource_id: str | None = None, actor_id: str | None = None,
    since: datetime | None = None, until: datetime | None = None,
    search: str | None = Query(None, max_length=120),
):
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.where(AuditLog.resource_id == resource_id)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if since:
        query = query.where(AuditLog.created_at >= since)
    if until:
        query = query.where(AuditLog.created_at <= until)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(AuditLog.summary.ilike(like), AuditLog.actor_email.ilike(like),
                                AuditLog.action.ilike(like)))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(AuditLog.seq.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[AuditOut](items=[AuditOut.model_validate(r) for r in rows],
                          meta=page_meta(int(total), page, page_size))


@router.get("/actions", summary="Known audit action codes")
def actions(user: Annotated[User, Depends(require(Perm.AUDIT_READ))]):
    return {"actions": sorted(str(a) for a in AuditAction)}


@router.get("/chain/verify", summary="Recompute the audit hash chain")
def verify(db: DbSession, user: Annotated[User, Depends(require(Perm.AUDIT_READ))],
           limit: int = Query(2000, ge=1, le=20000)):
    result = verify_chain(db, limit=limit)
    result["note"] = (
        "Each entry hashes its own canonical content together with the previous entry's hash. "
        "If any historic row were edited or removed, every hash after it would stop matching."
    )
    return result
