from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import document_detail, document_summary, run_payload
from app.core.config import PIPELINE_VERSION, RULES_VERSION, settings
from app.core.deps import CurrentUser, DbSession, RequestContext, require
from app.core.errors import (
    ConflictError,
    FileTooLarge,
    NotFoundError,
    PermissionDenied,
    ValidationFailure,
)
from app.core.ratelimit import limiter
from app.core.rbac import Perm
from app.core.security import sign_resource, verify_resource_signature
from app.db.enums import (
    DOCUMENT_TYPE_LABELS,
    REVIEW_ACTIONS_REQUIRING_REASON,
    AuditAction,
    ClaimStatus,
    DocumentSource,
    FindingStatus,
    InvestigationStatus,
    ProcessingStatus,
    ReviewAction,
    VerificationState,
)
from app.db.models.analysis import AnalysisRun
from app.db.models.claim import Claim
from app.db.models.document import Document, DocumentPage
from app.db.models.investigation import Investigation, ReviewActionRecord
from app.db.models.user import User
from app.schemas.common import Acknowledgement, Page, SignedUrl, page_meta
from app.schemas.core import (
    AnalyzeRequest,
    ClassificationOverride,
    DocumentDetailOut,
    DocumentOut,
    ReviewRequest,
    UploadResponse,
)
from app.services import audit, findings_store
from app.services.storage.factory import get_storage
from app.services.validation import validate_upload
from app.workers.queue import submit_analysis
from app.workers.tasks import analyze_document_task

router = APIRouter(prefix="/documents", tags=["documents"])

CHUNK = 1024 * 512


def _next_document_ref(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    count = db.execute(
        select(func.count()).select_from(Document)
    ).scalar_one()
    return f"DOC-{year}-{count + 1:06d}"


def _load(db: Session, document_id: str) -> Document:
    doc = db.execute(
        select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
    ).scalar_one_or_none()
    if doc is None:
        raise NotFoundError(f"No document with id {document_id}.")
    return doc


async def _read_upload(file: UploadFile) -> bytes:
    """Stream into memory with a hard ceiling, so an oversized body cannot exhaust RAM."""
    buffer = bytearray()
    while True:
        chunk = await file.read(CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > settings.max_upload_bytes + CHUNK:
            raise FileTooLarge(
                f"Upload exceeds the {settings.max_upload_mb} MB limit; transfer aborted."
            )
    return bytes(buffer)


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED,
             summary="Secure document upload")
async def upload_document(
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.DOCUMENT_UPLOAD))],
    file: Annotated[UploadFile, File(description="PDF, JPG, JPEG, PNG or TIFF")],
    claim_id: Annotated[str | None, Form()] = None,
    source: Annotated[str, Form()] = DocumentSource.PORTAL_UPLOAD,
    analyze: Annotated[bool, Form()] = True,
):
    limiter.check(f"upload:{user.id}", settings.rate_limit_upload)
    data = await _read_upload(file)

    # 1. Validate content before anything is persisted.
    validation = validate_upload(data, file.filename or "document", file.content_type)

    claim: Claim | None = None
    if claim_id:
        claim = db.execute(
            select(Claim).where(Claim.id == claim_id, Claim.deleted_at.is_(None))
        ).scalar_one_or_none()
        if claim is None:
            raise NotFoundError(f"No claim with id {claim_id}.")

    # 2. Hash immediately - the document identity is its content.
    from app.core.security import sha256_bytes

    digest = sha256_bytes(data)
    duplicate = db.execute(
        select(Document).where(Document.sha256 == digest, Document.deleted_at.is_(None))
    ).scalars().first()

    document_ref = _next_document_ref(db)
    now = datetime.now(timezone.utc)
    prefix = f"{now:%Y/%m}/{document_ref}"
    storage_key = f"{prefix}/original.{validation.normalized_extension}"

    storage = get_storage()
    storage.write("originals", storage_key, data, validation.detected_mime)

    doc = Document(
        document_ref=document_ref,
        claim_id=claim.id if claim else None,
        uploaded_by_id=user.id,
        original_filename=validation.safe_filename,
        storage_key=storage_key,
        artifact_prefix=prefix,
        mime_type=validation.detected_mime,
        declared_mime_type=file.content_type,
        file_extension=validation.normalized_extension,
        file_size=validation.size,
        sha256=digest,
        page_count=validation.page_count,
        source=source if source in set(DocumentSource) else DocumentSource.PORTAL_UPLOAD,
        uploaded_at=now,
        processing_status=ProcessingStatus.UPLOADED,
        processing_message="Uploaded and stored. Awaiting analysis.",
        verification_state=VerificationState.UNVERIFIED,
    )
    db.add(doc)
    db.flush()

    warnings = list(validation.warnings)
    if duplicate:
        warnings.append(
            f"An identical file (SHA-256 match) is already on record as "
            f"{duplicate.document_ref}"
            + (f" on claim {duplicate.claim.claim_number}" if duplicate.claim else "")
            + ". Both copies are retained; the analysis will raise a duplicate-content signal."
        )

    audit.record(
        db, action=AuditAction.DOCUMENT_UPLOADED, resource_type="document", resource_id=doc.id,
        actor=user,
        summary=(f"{document_ref} uploaded ({validation.detected_mime}, "
                 f"{validation.size} bytes, {validation.page_count} page(s))."),
        after={"document_ref": document_ref, "sha256": digest, "file_size": validation.size,
               "mime_type": validation.detected_mime, "claim_id": doc.claim_id,
               "page_count": validation.page_count},
        metadata={"warnings": warnings, "storage_provider": storage.name,
                  "duplicate_of": duplicate.document_ref if duplicate else None},
        **ctx,
    )

    analysis_info: dict = {"queued": False}
    if analyze:
        run = AnalysisRun(
            document_id=doc.id, claim_id=doc.claim_id, triggered_by_id=user.id,
            status=ProcessingStatus.QUEUED, pipeline_version=PIPELINE_VERSION,
            rules_version=RULES_VERSION, queue_mode=settings.queue_mode, stages=[],
        )
        db.add(run)
        db.flush()
        submission = submit_analysis(doc.id, actor_id=user.id, run_id=run.id)
        run.queue_mode = submission.mode
        run.queue_job_id = submission.job_id
        doc.processing_status = ProcessingStatus.QUEUED
        doc.processing_message = (
            "Queued for analysis." if submission.mode == "redis"
            else "Analysis running in-process (no Redis worker configured)."
        )
        if claim and claim.status == ClaimStatus.SUBMITTED:
            claim.status = ClaimStatus.PROCESSING
        analysis_info = {"queued": True, "analysis_run_id": run.id, "mode": submission.mode,
                         "job_id": submission.job_id, "detail": submission.detail}
        audit.record(
            db, action=AuditAction.ANALYSIS_STARTED, resource_type="document",
            resource_id=doc.id, actor=user,
            summary=f"Analysis queued for {document_ref} via {submission.mode}.",
            metadata=analysis_info, **ctx,
        )
        if submission.needs_inline_execution:
            background.add_task(analyze_document_task, doc.id, user.id, run.id)

    db.commit()
    db.refresh(doc)
    return UploadResponse(
        document=DocumentOut(**document_summary(db, doc)),
        analysis=analysis_info, warnings=warnings,
        message=(f"{document_ref} stored successfully. The original file is preserved unchanged."
                 + (" Analysis is under way." if analyze else "")),
    )


@router.get("", response_model=Page[DocumentOut], summary="List documents")
def list_documents(
    db: DbSession,
    user: Annotated[User, Depends(require(Perm.DOCUMENT_READ))],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    claim_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    risk_band: str | None = None,
    document_type: str | None = None,
    verification_state: str | None = None,
    search: str | None = Query(None, max_length=120),
    sort: str = Query("uploaded_at", pattern="^(uploaded_at|risk_score|document_ref)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    query = select(Document).where(Document.deleted_at.is_(None))
    if claim_id:
        query = query.where(Document.claim_id == claim_id)
    if status_filter:
        query = query.where(Document.processing_status == status_filter)
    if risk_band:
        query = query.where(Document.risk_band == risk_band)
    if document_type:
        query = query.where(Document.classification_type == document_type)
    if verification_state:
        query = query.where(Document.verification_state == verification_state)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(
            Document.document_ref.ilike(like),
            Document.original_filename.ilike(like),
            Document.sha256.ilike(like),
        ))
    total = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one()
    column = {"uploaded_at": Document.uploaded_at, "risk_score": Document.risk_score,
              "document_ref": Document.document_ref}[sort]
    query = query.order_by(column.desc() if order == "desc" else column.asc())
    rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return Page[DocumentOut](
        items=[DocumentOut(**document_summary(db, d)) for d in rows],
        meta=page_meta(int(total), page, page_size),
    )


@router.get("/{document_id}", response_model=DocumentDetailOut,
            summary="Full investigation payload for one document")
def get_document(
    document_id: str, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.DOCUMENT_READ))],
):
    doc = _load(db, document_id)
    audit.record(
        db, action=AuditAction.DOCUMENT_VIEWED, resource_type="document", resource_id=doc.id,
        actor=user, summary=f"{user.email} opened {doc.document_ref}.", **ctx,
    )
    return DocumentDetailOut(**document_detail(db, doc))


@router.get("/{document_id}/findings", summary="Findings for a document")
def get_findings(
    document_id: str, db: DbSession,
    user: Annotated[User, Depends(require(Perm.DOCUMENT_READ))],
    kind: str | None = None,
    severity: str | None = None,
    finding_status: str | None = Query(None, alias="status"),
):
    doc = _load(db, document_id)
    findings = findings_store.collect(db, doc.id, kinds=[kind] if kind else None)
    if severity:
        findings = [f for f in findings if f.severity == severity]
    if finding_status:
        findings = [f for f in findings if f.status == finding_status]
    return {
        "document_id": doc.id,
        "document_ref": doc.document_ref,
        "count": len(findings),
        "items": [f.as_dict() for f in findings],
        "provenance_legend": findings_store.SOURCE_OF_TRUTH,
    }


@router.get("/{document_id}/analysis", summary="Analysis runs and stage timeline")
def get_analysis(
    document_id: str, db: DbSession,
    user: Annotated[User, Depends(require(Perm.DOCUMENT_READ))],
):
    doc = _load(db, document_id)
    runs = db.execute(
        select(AnalysisRun).where(AnalysisRun.document_id == doc.id)
        .order_by(AnalysisRun.created_at.desc())
    ).scalars().all()
    return {
        "document_id": doc.id,
        "processing_status": doc.processing_status,
        "processing_message": doc.processing_message,
        "runs": [run_payload(r) for r in runs],
    }


@router.post("/{document_id}/analyze", summary="Run or re-run the analysis pipeline")
def analyze_document(
    document_id: str, payload: AnalyzeRequest, background: BackgroundTasks, db: DbSession,
    ctx: RequestContext, user: Annotated[User, Depends(require(Perm.DOCUMENT_ANALYZE))],
):
    doc = _load(db, document_id)
    if doc.processing_status in {ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING} \
            and not payload.force:
        raise ConflictError(
            "Analysis is already in progress for this document. Use force=true to requeue."
        )
    previous = db.execute(
        select(AnalysisRun).where(AnalysisRun.document_id == doc.id)
        .order_by(AnalysisRun.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    run = AnalysisRun(
        document_id=doc.id, claim_id=doc.claim_id, triggered_by_id=user.id,
        status=ProcessingStatus.QUEUED, pipeline_version=PIPELINE_VERSION,
        rules_version=RULES_VERSION, queue_mode=settings.queue_mode, stages=[],
        reprocess_of_id=previous.id if previous else None,
    )
    db.add(run)
    db.flush()
    submission = submit_analysis(doc.id, actor_id=user.id, run_id=run.id,
                                 reprocess_of=previous.id if previous else None)
    run.queue_mode = submission.mode
    run.queue_job_id = submission.job_id
    doc.processing_status = ProcessingStatus.QUEUED
    doc.processing_message = "Queued for analysis."
    audit.record(
        db, action=AuditAction.ANALYSIS_STARTED, resource_type="document", resource_id=doc.id,
        actor=user,
        summary=f"Analysis {'re-' if previous else ''}queued for {doc.document_ref}.",
        metadata={"analysis_run_id": run.id, "mode": submission.mode,
                  "reason": payload.reason, "reprocess_of": run.reprocess_of_id}, **ctx,
    )
    db.commit()
    if submission.needs_inline_execution:
        background.add_task(analyze_document_task, doc.id, user.id, run.id,
                            previous.id if previous else None)
    return {
        "ok": True, "analysis_run_id": run.id, "mode": submission.mode,
        "job_id": submission.job_id,
        "message": ("Analysis queued. Human review decisions on existing findings are preserved "
                    "across reprocessing."),
    }


@router.post("/{document_id}/classification", summary="Override the detected document type")
def override_classification(
    document_id: str, payload: ClassificationOverride, background: BackgroundTasks,
    db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.DOCUMENT_ANALYZE))],
):
    doc = _load(db, document_id)
    before = {"classification_type": doc.classification_type,
              "classification_confidence": doc.classification_confidence}
    doc.classification_type = payload.document_type
    doc.classification_confidence = 1.0
    doc.classification_detail = {
        **(doc.classification_detail or {}),
        "manual_override": {
            "by": user.email, "reason": payload.reason,
            "at": datetime.now(timezone.utc).isoformat(),
            "previous": before,
        },
    }
    audit.record(
        db, action=AuditAction.FINDING_MODIFIED, resource_type="document", resource_id=doc.id,
        actor=user,
        summary=(f"Document type for {doc.document_ref} set manually to "
                 f"{DOCUMENT_TYPE_LABELS[payload.document_type]}."),
        before=before, after={"classification_type": payload.document_type},
        metadata={"reason": payload.reason}, **ctx,
    )
    run_id = None
    if payload.reanalyze:
        run = AnalysisRun(
            document_id=doc.id, claim_id=doc.claim_id, triggered_by_id=user.id,
            status=ProcessingStatus.QUEUED, pipeline_version=PIPELINE_VERSION,
            rules_version=RULES_VERSION, queue_mode=settings.queue_mode, stages=[],
        )
        db.add(run)
        db.flush()
        run_id = run.id
        submission = submit_analysis(doc.id, actor_id=user.id, run_id=run.id)
        run.queue_mode = submission.mode
        db.commit()
        if submission.needs_inline_execution:
            background.add_task(analyze_document_task, doc.id, user.id, run.id)
    else:
        db.commit()
    return {"ok": True, "classification_type": doc.classification_type,
            "analysis_run_id": run_id,
            "message": "Document type updated. Type-specific rules will apply on re-analysis."}


# --------------------------------------------------------------------- review
@router.post("/{document_id}/review", summary="Record a human review action")
def review_document(
    document_id: str, payload: ReviewRequest, db: DbSession, ctx: RequestContext,
    user: CurrentUser,
):
    doc = _load(db, document_id)
    action = payload.action
    perm_map = {
        ReviewAction.CONFIRM_FINDING: Perm.FINDING_CONFIRM,
        ReviewAction.DISMISS_FINDING: Perm.FINDING_DISMISS,
        ReviewAction.REQUEST_INFORMATION: Perm.FINDING_REQUEST_INFO,
        ReviewAction.MARK_DOCUMENT_VERIFIED: Perm.DOCUMENT_VERIFY,
        ReviewAction.REJECT_DOCUMENT: Perm.DOCUMENT_VERIFY,
        ReviewAction.ESCALATE_INVESTIGATION: Perm.INVESTIGATION_ESCALATE,
    }
    require(perm_map[action])(user)

    reason = (payload.reason or "").strip()
    if action in REVIEW_ACTIONS_REQUIRING_REASON and len(reason) < 10:
        raise ValidationFailure(
            f"Action '{action}' changes the evidential record, so a written reason of at least "
            "10 characters is required."
        )

    finding_kind = None
    previous_status = None
    new_status = None
    finding_row = None

    if action in {ReviewAction.CONFIRM_FINDING, ReviewAction.DISMISS_FINDING,
                  ReviewAction.REQUEST_INFORMATION} and payload.finding_id:
        finding_kind, finding_row = findings_store.locate_finding(db, payload.finding_id)
        if finding_row is None:
            raise NotFoundError(f"No finding with id {payload.finding_id}.")
        if getattr(finding_row, "document_id", None) != doc.id:
            raise ValidationFailure("The finding does not belong to this document.")
        previous_status = finding_row.status
        new_status = {
            ReviewAction.CONFIRM_FINDING: FindingStatus.CONFIRMED,
            ReviewAction.DISMISS_FINDING: FindingStatus.DISMISSED,
            ReviewAction.REQUEST_INFORMATION: FindingStatus.INFORMATION_REQUESTED,
        }[action]
        finding_row.status = new_status
        finding_row.review_reason = reason or None
        finding_row.reviewed_by_id = user.id
    elif action in {ReviewAction.CONFIRM_FINDING, ReviewAction.DISMISS_FINDING}:
        raise ValidationFailure("finding_id is required for confirm/dismiss actions.")

    investigation = None
    if action == ReviewAction.MARK_DOCUMENT_VERIFIED:
        previous_status = doc.verification_state
        doc.verification_state = VerificationState.VERIFIED
        doc.verified_by_id = user.id
        doc.verified_at = datetime.now(timezone.utc)
        doc.verification_note = reason
        new_status = doc.verification_state
    elif action == ReviewAction.REJECT_DOCUMENT:
        previous_status = doc.verification_state
        doc.verification_state = VerificationState.REJECTED
        doc.verified_by_id = user.id
        doc.verified_at = datetime.now(timezone.utc)
        doc.verification_note = reason
        new_status = doc.verification_state
    elif action == ReviewAction.REQUEST_INFORMATION:
        previous_status = previous_status or doc.verification_state
        doc.verification_state = VerificationState.INFORMATION_REQUESTED
        new_status = new_status or doc.verification_state
    elif action == ReviewAction.ESCALATE_INVESTIGATION:
        if not doc.claim_id:
            raise ValidationFailure("Only documents attached to a claim can be escalated.")
        investigation = db.execute(
            select(Investigation).where(Investigation.claim_id == doc.claim_id,
                                        Investigation.status != InvestigationStatus.CLOSED)
            .order_by(Investigation.created_at.desc())
        ).scalars().first()
        if investigation is None:
            claim = db.get(Claim, doc.claim_id)
            investigation = Investigation(
                case_number=f"INV-{datetime.now(timezone.utc).year}-"
                            f"{claim.claim_number[-6:] if claim else doc.document_ref[-6:]}",
                claim_id=doc.claim_id, document_id=doc.id,
                title=f"Escalated review of {doc.document_ref}",
                status=InvestigationStatus.ESCALATED,
                priority=payload.escalate_priority or "high",
                assigned_to_id=payload.assign_to_id, opened_by_id=user.id,
                opened_at=datetime.now(timezone.utc), risk_score_at_open=doc.risk_score,
                summary=reason, context={"opened_by": "manual_escalation"},
            )
            db.add(investigation)
        else:
            previous_status = investigation.status
            investigation.status = InvestigationStatus.ESCALATED
            investigation.priority = payload.escalate_priority or investigation.priority
            if payload.assign_to_id:
                investigation.assigned_to_id = payload.assign_to_id
        new_status = InvestigationStatus.ESCALATED
        claim = db.get(Claim, doc.claim_id)
        if claim and claim.status != ClaimStatus.RESOLVED:
            claim.status = ClaimStatus.INVESTIGATION
        db.flush()

    # Marking documents verified can clear the whole claim - but only when every
    # document has a human verdict, and never for a resolved claim.
    if action in {ReviewAction.MARK_DOCUMENT_VERIFIED, ReviewAction.REJECT_DOCUMENT} \
            and doc.claim_id:
        claim = db.get(Claim, doc.claim_id)
        if claim and claim.status not in {ClaimStatus.RESOLVED, ClaimStatus.INVESTIGATION}:
            siblings = db.execute(
                select(Document).where(Document.claim_id == claim.id,
                                       Document.deleted_at.is_(None))
            ).scalars().all()
            if any(d.verification_state == VerificationState.REJECTED for d in siblings):
                claim.status = ClaimStatus.REVIEW_REQUIRED
            elif all(d.verification_state == VerificationState.VERIFIED for d in siblings):
                claim.status = ClaimStatus.VERIFIED

    record = ReviewActionRecord(
        document_id=doc.id, claim_id=doc.claim_id,
        investigation_id=investigation.id if investigation else None,
        finding_kind=finding_kind, finding_id=payload.finding_id, action=action,
        reason=reason or None, actor_id=user.id, actor_role=user.role_name,
        previous_status=previous_status, new_status=new_status,
        context={"escalate_priority": payload.escalate_priority,
                 "assign_to_id": payload.assign_to_id},
    )
    db.add(record)

    audit.record(
        db, action=AuditAction.REVIEW_ACTION, resource_type="document", resource_id=doc.id,
        actor=user,
        summary=f"{user.email} recorded '{action}' on {doc.document_ref}.",
        before={"status": previous_status}, after={"status": new_status},
        metadata={"finding_id": payload.finding_id, "finding_kind": finding_kind,
                  "reason_supplied": bool(reason), "action": action}, **ctx,
    )
    if finding_row is not None:
        audit.record(
            db, action=AuditAction.FINDING_MODIFIED, resource_type="finding",
            resource_id=payload.finding_id, actor=user,
            summary=(f"Finding {finding_row.finding_code} on {doc.document_ref} marked "
                     f"{new_status}."),
            before={"status": previous_status}, after={"status": new_status},
            metadata={"reason": reason[:400]}, **ctx,
        )
    db.commit()
    return {
        "ok": True, "action": action, "document_id": doc.id,
        "finding_status": new_status,
        "investigation_id": investigation.id if investigation else None,
        "message": ("Recorded. The risk score will exclude dismissed findings and treat confirmed "
                    "findings as established on the next assessment."),
    }


@router.post("/{document_id}/reassess", summary="Recompute the risk score after review")
def reassess(
    document_id: str, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.DOCUMENT_ANALYZE))],
):
    from app.db.models.analysis import RiskAssessment
    from app.db.models.config import DetectionRule, SystemSetting
    from app.services.risk import engine as risk_engine

    doc = _load(db, document_id)
    findings = findings_store.collect(db, doc.id)
    inputs = [
        risk_engine.FindingInput(
            code=f.code, category=f.category, severity=f.severity, confidence=f.confidence,
            title=f.title, kind=f.kind, finding_id=f.finding_id, detector=f.detector,
            model_version=f.model_version, status=f.status, page=f.page,
        )
        for f in findings if f.code != "AIGC_NO_SIGNIFICANT_INDICATORS"
    ]
    verification_inputs = findings_store.latest_verification_inputs(db, doc.id)
    weights = {r.code: r.weight for r in
               db.execute(select(DetectionRule).where(DetectionRule.enabled.is_(True)))
               .scalars().all()}
    setting = db.execute(
        select(SystemSetting).where(SystemSetting.key == "risk_thresholds")
    ).scalar_one_or_none()
    previous = doc.risk_score
    result = risk_engine.assess(
        inputs, verification_inputs, rule_weights=weights,
        thresholds=setting.value if setting else None,
        stage_coverage={"recomputed_after_review": True},
    )
    for prior in db.execute(
        select(RiskAssessment).where(RiskAssessment.document_id == doc.id,
                                     RiskAssessment.is_superseded.is_(False))
    ).scalars().all():
        prior.is_superseded = True
    db.add(RiskAssessment(
        document_id=doc.id, claim_id=doc.claim_id, score=result.score, band=result.band,
        weights_version=result.weights_version,
        signals=[s.as_dict() for s in result.signals],
        category_scores=result.category_scores, top_reasons=result.top_reasons,
        explanation=result.explanation, interpretation_note=result.interpretation_note,
        coverage={**result.coverage, "mitigations": result.mitigations},
    ))
    doc.risk_score, doc.risk_band = result.score, result.band
    audit.record(
        db, action=AuditAction.ANALYSIS_COMPLETED, resource_type="document", resource_id=doc.id,
        actor=user, summary=(f"Risk reassessed for {doc.document_ref} after review: "
                             f"{previous} -> {result.score}."),
        before={"risk_score": previous}, after={"risk_score": result.score,
                                                "risk_band": result.band},
        metadata={"dismissed_excluded": result.dismissed_count}, **ctx,
    )
    db.commit()
    return {"ok": True, "risk": result.as_dict()}


# ----------------------------------------------------------------- file access
@router.post("/{document_id}/links", response_model=list[SignedUrl],
             summary="Mint short-lived signed links for the viewer")
def create_links(
    document_id: str, db: DbSession,
    user: Annotated[User, Depends(require(Perm.DOCUMENT_DOWNLOAD))],
):
    doc = _load(db, document_id)
    out: list[SignedUrl] = []
    for purpose, path in [("original", f"{settings.api_prefix}/documents/{doc.id}/file")]:
        signed = sign_resource(doc.id, purpose, user.id)
        out.append(SignedUrl(
            url=(f"{path}?exp={signed['exp']}&nonce={signed['nonce']}&sig={signed['sig']}"
                 f"&uid={user.id}"),
            expires_at=datetime.fromtimestamp(signed["exp"], tz=timezone.utc), purpose=purpose,
        ))
    pages = db.execute(
        select(DocumentPage).where(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number)
    ).scalars().all()
    for page in pages:
        signed = sign_resource(f"{doc.id}:{page.page_number}", "page_render", user.id)
        out.append(SignedUrl(
            url=(f"{settings.api_prefix}/documents/{doc.id}/pages/{page.page_number}/render"
                 f"?exp={signed['exp']}&nonce={signed['nonce']}&sig={signed['sig']}"
                 f"&uid={user.id}"),
            expires_at=datetime.fromtimestamp(signed["exp"], tz=timezone.utc),
            purpose=f"page_render:{page.page_number}",
        ))
    return out


def _authorise_binary(
    request: Request, db: Session, resource: str, purpose: str,
    exp: int | None, nonce: str | None, sig: str | None, uid: str | None,
) -> User:
    """Accept either a signed link or a normal authenticated session."""
    if sig and exp and nonce and uid:
        verify_resource_signature(resource, purpose, uid, exp, nonce, sig)
        user = db.get(User, uid)
        if user is None or not user.is_active:
            raise PermissionDenied("The signing user is no longer active.")
        return user
    from app.core.deps import get_current_user

    user = get_current_user(request, db, None)
    require(Perm.DOCUMENT_DOWNLOAD)(user)
    return user


@router.get("/{document_id}/file", summary="Stream the original document")
def download_original(
    document_id: str, request: Request, db: DbSession, ctx: RequestContext,
    exp: int | None = None, nonce: str | None = None, sig: str | None = None,
    uid: str | None = None, disposition: str = Query("inline", pattern="^(inline|attachment)$"),
):
    doc = _load(db, document_id)
    user = _authorise_binary(request, db, doc.id, "original", exp, nonce, sig, uid)
    storage = get_storage()
    data = storage.read("originals", doc.storage_key)
    audit.record(
        db, action=AuditAction.DOCUMENT_DOWNLOADED, resource_type="document", resource_id=doc.id,
        actor=user,
        summary=f"{user.email} retrieved the original bytes of {doc.document_ref}.",
        metadata={"disposition": disposition, "via_signed_link": bool(sig)}, **ctx,
    )
    db.commit()
    filename = doc.original_filename.replace('"', "")
    return Response(
        content=data, media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "X-Document-SHA256": doc.sha256,
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{document_id}/pages/{page_number}/render",
            summary="Stream a rendered page or a forensic overlay layer")
def render_page(
    document_id: str, page_number: int, request: Request, db: DbSession,
    layer: str = Query("page", max_length=24),
    exp: int | None = None, nonce: str | None = None, sig: str | None = None,
    uid: str | None = None,
):
    doc = _load(db, document_id)
    _authorise_binary(db=db, request=request, resource=f"{doc.id}:{page_number}",
                      purpose="page_render", exp=exp, nonce=nonce, sig=sig, uid=uid)
    page = db.execute(
        select(DocumentPage).where(DocumentPage.document_id == doc.id,
                                   DocumentPage.page_number == page_number)
    ).scalar_one_or_none()
    if page is None:
        raise NotFoundError(f"Page {page_number} has not been rendered for this document.")
    if layer == "page":
        key = page.render_key
    else:
        key = (page.artifacts or {}).get(layer)
    if not key:
        raise NotFoundError(
            f"Layer '{layer}' is not available for page {page_number}. "
            f"Available: {sorted((page.artifacts or {}).keys()) + ['page']}."
        )
    storage = get_storage()
    data = storage.read("artifacts", key)
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=120"})


@router.delete("/{document_id}", response_model=Acknowledgement,
               summary="Soft-delete a document")
def delete_document(
    document_id: str, db: DbSession, ctx: RequestContext,
    reason: str = Query(..., min_length=10, max_length=500),
    user: Annotated[User, Depends(require(Perm.DOCUMENT_DELETE))] = None,
):
    doc = _load(db, document_id)
    doc.deleted_at = datetime.now(timezone.utc)
    audit.record(
        db, action=AuditAction.DOCUMENT_DELETED, resource_type="document", resource_id=doc.id,
        actor=user, summary=f"{doc.document_ref} soft-deleted by {user.email}.",
        before={"deleted_at": None}, after={"deleted_at": doc.deleted_at.isoformat()},
        metadata={"reason": reason,
                  "note": "Stored bytes retained until the retention job purges them."}, **ctx,
    )
    db.commit()
    return Acknowledgement(
        message=("Document soft-deleted and hidden from listings. The stored original is retained "
                 "until the retention policy purges it, so the evidence chain is not broken.")
    )
