from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.serializers import verification_payload
from app.core.deps import DbSession, RequestContext, require
from app.core.errors import NotFoundError, ProviderUnavailable, ValidationFailure
from app.core.rbac import Perm
from app.db.enums import AuditAction, VerificationOutcome
from app.db.models.claim import Claim
from app.db.models.document import Document, ExtractedField
from app.db.models.user import User
from app.db.models.verification import VerificationRequest, VerificationResult
from app.schemas.common import Page, page_meta
from app.schemas.core import VerificationRunRequest
from app.services import audit
from app.services.verification.base import VerificationQuery, VerificationResponse
from app.services.verification.factory import (
    PLAN_BY_DOCUMENT_TYPE,
    REQUEST_PAYLOAD_FIELDS,
    get_verification_provider,
    list_verification_providers,
)

router = APIRouter(prefix="/verification", tags=["verification"])


@router.get("/providers", summary="Configured verification providers")
def providers(user: Annotated[User, Depends(require(Perm.VERIFICATION_READ))]):
    return {
        "providers": list_verification_providers(),
        "routing": PLAN_BY_DOCUMENT_TYPE,
        "note": ("Providers marked is_demo answer from a bundled sample registry. No external "
                 "system is contacted and their results must not be presented as real-world "
                 "confirmations."),
    }


@router.get("/requests", response_model=Page[dict], summary="Verification history")
def list_requests(
    db: DbSession, user: Annotated[User, Depends(require(Perm.VERIFICATION_READ))],
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    document_id: str | None = None, claim_id: str | None = None,
    outcome: str | None = None, request_type: str | None = None,
):
    query = select(VerificationRequest)
    if document_id:
        query = query.where(VerificationRequest.document_id == document_id)
    if claim_id:
        query = query.where(VerificationRequest.claim_id == claim_id)
    if request_type:
        query = query.where(VerificationRequest.request_type == request_type)
    if outcome:
        query = query.join(VerificationResult).where(VerificationResult.outcome == outcome)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(VerificationRequest.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    items = []
    for row in rows:
        payload = verification_payload(row)
        doc = db.get(Document, row.document_id) if row.document_id else None
        claim = db.get(Claim, row.claim_id) if row.claim_id else None
        payload["document_ref"] = doc.document_ref if doc else None
        payload["claim_number"] = claim.claim_number if claim else None
        items.append(payload)
    return Page[dict](items=items, meta=page_meta(int(total), page, page_size))


def _values_for(db, doc: Document) -> dict:
    rows = db.execute(
        select(ExtractedField).where(ExtractedField.document_id == doc.id)
    ).scalars().all()
    values: dict[str, str] = {}
    for row in sorted(rows, key=lambda r: -(r.confidence or 0)):
        if row.group_name == "line_items":
            continue
        value = row.value_normalized or row.value_raw
        if value and row.field_key not in values:
            values[row.field_key] = value
    if doc.claim:
        values.setdefault("policy_number", doc.claim.policy_number)
        values.setdefault("customer_name", doc.claim.customer_name)
        if doc.claim.customer_dob:
            values.setdefault("date_of_birth", doc.claim.customer_dob.isoformat())
        if doc.claim.claimed_amount:
            values.setdefault("claimed_amount", str(doc.claim.claimed_amount))
    return values


@router.post("/documents/{document_id}/run", summary="Run trusted-source verification on demand")
def run_verification(
    document_id: str, payload: VerificationRunRequest, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.VERIFICATION_RUN))],
):
    doc = db.execute(
        select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
    ).scalar_one_or_none()
    if doc is None:
        raise NotFoundError(f"No document with id {document_id}.")

    plan = payload.request_types or PLAN_BY_DOCUMENT_TYPE.get(
        doc.classification_type or "other", []
    )
    if not plan:
        raise ValidationFailure(
            "No verification route applies to this document type. Supply request_types "
            f"explicitly. Known types: {sorted(REQUEST_PAYLOAD_FIELDS)}."
        )
    values = {**_values_for(db, doc), **payload.overrides}
    service_date = values.get("treatment_date") or values.get("invoice_date")

    results = []
    for request_type in plan:
        if request_type not in REQUEST_PAYLOAD_FIELDS:
            raise ValidationFailure(f"Unknown verification request type '{request_type}'.")
        request_payload = {k: values[k] for k in REQUEST_PAYLOAD_FIELDS[request_type]
                           if k in values}
        if not request_payload:
            results.append({"request_type": request_type, "skipped": True,
                            "reason": "No usable reference was extracted for this check."})
            continue
        if service_date:
            request_payload.setdefault("service_date", service_date)
        provider = get_verification_provider(request_type)
        record = VerificationRequest(
            document_id=doc.id, claim_id=doc.claim_id, requested_by_id=user.id,
            provider_key=provider.key, provider_label=provider.label,
            provider_mode=provider.mode, request_type=request_type,
            request_payload=request_payload, status="pending", trigger="manual",
        )
        db.add(record)
        db.flush()
        audit.record(
            db, action=AuditAction.VERIFICATION_REQUESTED, resource_type="document",
            resource_id=doc.id, actor=user,
            summary=(f"{provider.label} {request_type} requested for {doc.document_ref}."),
            metadata={"request_type": request_type, "provider": provider.key,
                      "mode": provider.mode, "fields": sorted(request_payload)}, **ctx,
        )
        try:
            response = provider.verify(VerificationQuery(
                request_type=request_type, payload=request_payload,
                document_id=doc.id, claim_id=doc.claim_id,
            ))
            record.status = "completed"
        except ProviderUnavailable as exc:
            record.status = "unavailable"
            response = VerificationResponse(
                outcome=VerificationOutcome.UNAVAILABLE,
                summary=("The verification provider could not be reached. Nothing was changed; "
                         "retry when the provider is available."),
                is_demo_data=provider.mode == "demo", error=exc.message,
            )
        result_row = VerificationResult(
            request_id=record.id, outcome=response.outcome, summary=response.summary,
            checks=[c.as_dict() for c in response.checks], raw_response=response.raw,
            latency_ms=response.latency_ms, reference_id=response.reference_id,
            is_demo_data=response.is_demo_data,
            data_source_disclaimer=response.disclaimer, error=response.error,
        )
        db.add(result_row)
        db.flush()
        audit.record(
            db, action=AuditAction.VERIFICATION_COMPLETED, resource_type="document",
            resource_id=doc.id, actor=user,
            summary=f"{provider.label} {request_type} -> {response.outcome}.",
            after={"outcome": response.outcome, "reference_id": response.reference_id},
            metadata={"is_demo_data": response.is_demo_data,
                      "failed_checks": [c.label for c in response.failed_checks]}, **ctx,
        )
        results.append(verification_payload(record))
    db.commit()
    return {
        "document_id": doc.id, "document_ref": doc.document_ref, "results": results,
        "message": ("Verification complete. Run 'reassess' to fold the outcome into the risk "
                    "score."),
    }
