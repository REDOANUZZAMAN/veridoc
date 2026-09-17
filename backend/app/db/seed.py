"""Database bootstrap and deterministic demo seeding.

    python -m app.db.seed --reset            # drop, recreate, seed reference + demo
    python -m app.db.seed                    # seed/refresh without dropping
    python -m app.db.seed --reference-only   # roles, users, rules, providers, settings
    python -m app.db.seed --no-analysis      # seed documents but skip the pipeline

Demo documents are *rendered* (see ``demo_documents.py``) and then ingested
through the same validation, hashing and storage path as a real upload, so the
demo exercises the production code rather than hand-written fixtures.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import PIPELINE_VERSION, RULES_VERSION, settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password, sha256_bytes
from app.db.base import Base
from app.db.demo_documents import render
from app.db.demo_scenarios import CLAIMS, REVIEW_SCRIPT
from app.db.enums import (
    AuditAction,
    ClaimStatus,
    FindingStatus,
    InvestigationStatus,
    ProcessingStatus,
    RiskBand,
    VerificationState,
)
from app.db.models import (  # noqa: F401  (import registers every table)
    AnalysisRun,
    AuditLog,
    Claim,
    DetectionRule,
    Document,
    Investigation,
    InvestigationNote,
    ProviderConfig,
    Report,
    ReviewActionRecord,
    RiskAssessment,
    RoleDefinition,
    SystemSetting,
    User,
)
from app.db.seed_data import (
    DEMO_USERS,
    DETECTOR_RULES,
    SYSTEM_SETTINGS,
    provider_rows,
    role_rows,
    stable_id,
)
from app.db.session import SessionLocal, engine
from app.services import audit, findings_store
from app.services.consistency.engine import rule_catalogue
from app.services.storage.factory import get_storage
from app.services.validation import validate_upload

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
def _alembic_config():
    """Alembic configuration pointed at this installation's database."""
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def _has_table(name: str) -> bool:
    return inspect(engine).has_table(name)


def create_schema() -> None:
    """Bring the database to head, however it was created.

    The seeder and Alembic must not disagree about who owns the schema, or a
    container that runs `alembic upgrade head` on start will fail against a
    database the seeder built. So:

      * empty database        -> run the migrations, exactly as production does
      * tables but no version -> stamp head (a database built by an older seed)
      * already versioned     -> upgrade to head
    """
    from alembic import command

    config = _alembic_config()
    versioned = _has_table("alembic_version")
    populated = _has_table("documents")

    if not versioned and populated:
        command.stamp(config, "head")
        logger.info("schema_stamped_at_head")
    else:
        command.upgrade(config, "head")
        logger.info("schema_migrated", extra={"tables": len(Base.metadata.tables)})


def reset_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    logger.info("schema_dropped")
    create_schema()


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #
def seed_roles(db: Session) -> None:
    for row in role_rows():
        existing = db.execute(
            select(RoleDefinition).where(RoleDefinition.name == row["name"])
        ).scalar_one_or_none()
        if existing:
            existing.label, existing.description = row["label"], row["description"]
            existing.permissions = row["permissions"]
        else:
            db.add(RoleDefinition(**row))
    db.flush()


def seed_users(db: Session) -> list[User]:
    created = []
    for spec in DEMO_USERS:
        existing = db.execute(
            select(User).where(User.email == spec["email"])
        ).scalar_one_or_none()
        if existing:
            created.append(existing)
            continue
        user = User(
            id=stable_id("user", spec["email"]), email=spec["email"],
            full_name=spec["full_name"], role_name=str(spec["role"]),
            password_hash=hash_password(settings.seed_password),
            job_title=spec["job_title"], team=spec["team"], is_active=True,
            must_change_password=False,
        )
        db.add(user)
        created.append(user)
    db.flush()
    return created


def seed_rules(db: Session) -> None:
    catalogue = {
        entry["code"]: entry for entry in rule_catalogue()
    }
    # 1. consistency rules, straight from the engine's own catalogue
    for code, entry in catalogue.items():
        existing = db.execute(
            select(DetectionRule).where(DetectionRule.code == code)
        ).scalar_one_or_none()
        payload = dict(
            code=code, name=entry["name"], category="consistency",
            description=entry["description"], default_severity=entry["default_severity"],
            weight=entry["weight"], enabled=True, applies_to=entry["applies_to"],
            params=entry["params"], version=entry["version"], is_system=True,
        )
        if existing:
            for key, value in payload.items():
                if key not in {"enabled", "weight", "default_severity", "params"}:
                    setattr(existing, key, value)
        else:
            db.add(DetectionRule(id=stable_id("rule", code), **payload))
    # 2. detector / verification / tampering weights
    for code, name, category, severity, weight, description in DETECTOR_RULES:
        if code in catalogue:
            continue
        existing = db.execute(
            select(DetectionRule).where(DetectionRule.code == code)
        ).scalar_one_or_none()
        payload = dict(
            code=code, name=name, category=category, description=description,
            default_severity=str(severity), weight=weight, enabled=True, applies_to=[],
            params={}, version=RULES_VERSION, is_system=True,
        )
        if existing:
            existing.name, existing.description = name, description
            existing.category = category
        else:
            db.add(DetectionRule(id=stable_id("rule", code), **payload))
    db.flush()


def seed_providers(db: Session) -> None:
    for row in provider_rows():
        existing = db.execute(
            select(ProviderConfig).where(ProviderConfig.kind == row["kind"],
                                         ProviderConfig.key == row["key"])
        ).scalar_one_or_none()
        payload = {
            "kind": str(row["kind"]), "key": row["key"], "label": row["label"],
            "description": row.get("description", ""), "is_demo": row.get("is_demo", True),
            "credential_env_keys": row.get("credential_env_keys", []),
            "settings_json": row.get("settings_json", {}),
            "model_name": row.get("model_name"), "model_version": row.get("model_version"),
            "health_status": "ready" if row.get("is_active") else "configured",
        }
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
        else:
            db.add(ProviderConfig(
                id=stable_id("provider", f"{row['kind']}:{row['key']}"),
                is_active=row.get("is_active", False), **payload,
            ))
    db.flush()


def seed_settings(db: Session) -> None:
    for row in SYSTEM_SETTINGS:
        existing = db.execute(
            select(SystemSetting).where(SystemSetting.key == row["key"])
        ).scalar_one_or_none()
        if existing:
            existing.label, existing.description = row["label"], row["description"]
        else:
            db.add(SystemSetting(id=stable_id("setting", row["key"]), **row))
    db.flush()


def seed_reference(db: Session) -> None:
    seed_roles(db)
    seed_users(db)
    seed_rules(db)
    seed_providers(db)
    seed_settings(db)
    audit.record(
        db, action=AuditAction.SETTING_UPDATED, resource_type="system",
        resource_id="seed", summary="Reference data seeded (roles, users, rules, providers).",
        metadata={"pipeline_version": PIPELINE_VERSION, "rules_version": RULES_VERSION},
    )
    logger.info("reference_seeded")


# --------------------------------------------------------------------------- #
# Demo claims and documents
# --------------------------------------------------------------------------- #
def seed_demo(db: Session, *, analyse: bool = True) -> dict:
    storage = get_storage()
    users = {u.email: u for u in db.execute(select(User)).scalars().all()}
    rendered_cache: dict[str, bytes] = {}
    counters = {"claims": 0, "documents": 0, "analysed": 0}
    doc_index = db.execute(select(Document)).scalars().all()
    next_ref = len(doc_index) + 1

    for demo_claim in CLAIMS:
        claim = db.execute(
            select(Claim).where(Claim.claim_number == demo_claim.claim_number)
        ).scalar_one_or_none()
        creator = users.get(demo_claim.created_by)
        investigator = users.get(demo_claim.assigned_investigator or "")
        if claim is None:
            claim = Claim(
                id=stable_id("claim", demo_claim.claim_number),
                claim_number=demo_claim.claim_number,
                customer_name=demo_claim.customer_name, customer_dob=demo_claim.customer_dob,
                customer_email=demo_claim.customer_email,
                policy_number=demo_claim.policy_number, claim_type=demo_claim.claim_type,
                incident_date=demo_claim.incident_date,
                claimed_amount=demo_claim.claimed_amount, currency=demo_claim.currency,
                summary=demo_claim.summary, status=ClaimStatus.SUBMITTED,
                submitted_at=datetime.combine(
                    demo_claim.incident_date, datetime.min.time()).replace(
                        tzinfo=timezone.utc) + timedelta(days=3),
                created_by_id=creator.id if creator else None,
                assigned_investigator_id=investigator.id if investigator else None,
                context={"seeded": True},
            )
            db.add(claim)
            db.flush()
            counters["claims"] += 1
            audit.record(
                db, action=AuditAction.CLAIM_CREATED, resource_type="claim",
                resource_id=claim.id, actor=creator,
                summary=f"Demo claim {claim.claim_number} created.",
                after={"claim_number": claim.claim_number,
                       "policy_number": claim.policy_number,
                       "claimed_amount": str(claim.claimed_amount)},
                metadata={"seeded": True},
            )

        for demo_doc in demo_claim.documents:
            existing = db.execute(
                select(Document).where(Document.claim_id == claim.id,
                                       Document.original_filename == demo_doc.filename)
            ).scalar_one_or_none()
            if existing is not None:
                continue

            if demo_doc.duplicate_of:
                data = rendered_cache[demo_doc.duplicate_of]
                extension, mime = ("pdf", "application/pdf")
            else:
                data, extension, mime = render(demo_doc.spec)
                rendered_cache[demo_doc.spec.key] = data

            validation = validate_upload(data, demo_doc.filename, mime)
            uploader = users.get(demo_doc.uploaded_by) or creator
            document_ref = f"DOC-2026-{next_ref:06d}"
            next_ref += 1
            prefix = f"{demo_doc.uploaded_at:%Y/%m}/{document_ref}"
            key = f"{prefix}/original.{validation.normalized_extension}"
            storage.write("originals", key, data, validation.detected_mime)

            document = Document(
                id=stable_id("document", document_ref),
                document_ref=document_ref, claim_id=claim.id,
                uploaded_by_id=uploader.id if uploader else None,
                original_filename=validation.safe_filename, storage_key=key,
                artifact_prefix=prefix, mime_type=validation.detected_mime,
                declared_mime_type=mime, file_extension=validation.normalized_extension,
                file_size=validation.size, sha256=sha256_bytes(data),
                page_count=validation.page_count, source="seed_demo",
                uploaded_at=demo_doc.uploaded_at,
                processing_status=ProcessingStatus.UPLOADED,
                processing_message="Seeded demo document. Awaiting analysis.",
                verification_state=VerificationState.UNVERIFIED,
            )
            db.add(document)
            db.flush()
            counters["documents"] += 1
            audit.record(
                db, action=AuditAction.DOCUMENT_UPLOADED, resource_type="document",
                resource_id=document.id, actor=uploader,
                summary=(f"{document_ref} seeded for {claim.claim_number} "
                         f"({demo_doc.scenario or 'baseline'})."),
                after={"document_ref": document_ref, "sha256": document.sha256,
                       "file_size": document.file_size, "mime_type": document.mime_type},
                metadata={"scenario": demo_doc.scenario, "seeded": True,
                          "warnings": validation.warnings},
            )
    db.commit()

    if analyse:
        from app.services.pipeline import run_analysis

        documents = db.execute(
            select(Document).where(Document.source == "seed_demo")
            .order_by(Document.uploaded_at, Document.document_ref)
        ).scalars().all()
        for document in documents:
            if document.processing_status in {ProcessingStatus.ANALYZED,
                                              ProcessingStatus.PARTIAL,
                                              ProcessingStatus.QUARANTINED}:
                continue
            actor = document.uploaded_by
            try:
                run_analysis(db, document.id, actor=actor)
                db.commit()
                counters["analysed"] += 1
                logger.info("seed_document_analysed",
                            extra={"document": document.document_ref,
                                   "status": document.processing_status,
                                   "risk": document.risk_score})
            except Exception as exc:
                db.rollback()
                logger.error("seed_document_analysis_failed",
                             extra={"document": document.document_ref,
                                    "detail": str(exc)[:300]})
    return counters


# --------------------------------------------------------------------------- #
# Scripted human review, so the demo has real investigation history
# --------------------------------------------------------------------------- #
DISMISS_PREFERENCE = ("TAMPER_COPY_PASTE_REGION", "IMG_COPY_MOVE_REGION")


def apply_review_script(db: Session) -> dict:
    from app.api.routes.documents import reassess  # noqa: F401  (documented behaviour)

    users = {u.email: u for u in db.execute(select(User)).scalars().all()}
    applied = {"verified": 0, "confirmed": 0, "dismissed": 0, "notes": 0, "decisions": 0}

    for claim_number, actor_email, action, target, reason in REVIEW_SCRIPT:
        claim = db.execute(
            select(Claim).where(Claim.claim_number == claim_number)
        ).scalar_one_or_none()
        actor = users.get(actor_email)
        if claim is None or actor is None:
            continue
        documents = db.execute(
            select(Document).where(Document.claim_id == claim.id)
            .order_by(Document.document_ref)
        ).scalars().all()
        if not documents:
            continue

        if action == "mark_document_verified":
            for document in documents:
                if document.risk_band != RiskBand.LOW_CONCERN:
                    continue
                document.verification_state = VerificationState.VERIFIED
                document.verified_by_id = actor.id
                document.verified_at = datetime.now(timezone.utc)
                document.verification_note = reason
                db.add(ReviewActionRecord(
                    document_id=document.id, claim_id=claim.id,
                    action="mark_document_verified", reason=reason, actor_id=actor.id,
                    actor_role=actor.role_name, previous_status="unverified",
                    new_status="verified", context={"seeded": True},
                ))
                audit.record(
                    db, action=AuditAction.REVIEW_ACTION, resource_type="document",
                    resource_id=document.id, actor=actor,
                    summary=f"{actor.email} marked {document.document_ref} verified.",
                    before={"verification_state": "unverified"},
                    after={"verification_state": "verified"},
                    metadata={"reason": reason[:400], "seeded": True},
                )
                applied["verified"] += 1

        elif action == "claim_decision":
            claim.decision = target
            claim.decision_reason = reason
            claim.decided_at = datetime.now(timezone.utc)
            claim.decided_by_id = actor.id
            claim.status = ClaimStatus.RESOLVED
            audit.record(
                db, action=AuditAction.CLAIM_DECISION, resource_type="claim",
                resource_id=claim.id, actor=actor,
                summary=f"Claim {claim.claim_number} decision '{target}' recorded.",
                after={"decision": target, "status": claim.status},
                metadata={"reason": reason[:400], "seeded": True},
            )
            applied["decisions"] += 1

        elif action in {"confirm_top_finding", "dismiss_weakest_finding"}:
            candidates = []
            for document in documents:
                for finding in findings_store.collect(db, document.id):
                    if finding.status != FindingStatus.OPEN:
                        continue
                    candidates.append((document, finding))
            if not candidates:
                continue
            if action == "confirm_top_finding":
                order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
                document, finding = min(
                    candidates, key=lambda pair: (order.get(pair[1].severity, 9),
                                                  -pair[1].confidence))
                new_status = FindingStatus.CONFIRMED
                applied["confirmed"] += 1
            else:
                preferred = [c for c in candidates if c[1].code in DISMISS_PREFERENCE]
                document, finding = (preferred or candidates)[0]
                new_status = FindingStatus.DISMISSED
                applied["dismissed"] += 1

            kind, row = findings_store.locate_finding(db, finding.finding_id)
            if row is None:
                continue
            previous = row.status
            row.status = new_status
            row.review_reason = reason
            row.reviewed_by_id = actor.id
            db.add(ReviewActionRecord(
                document_id=document.id, claim_id=claim.id, finding_kind=kind,
                finding_id=finding.finding_id,
                action=("confirm_finding" if new_status == FindingStatus.CONFIRMED
                        else "dismiss_finding"),
                reason=reason, actor_id=actor.id, actor_role=actor.role_name,
                previous_status=previous, new_status=new_status, context={"seeded": True},
            ))
            audit.record(
                db, action=AuditAction.FINDING_MODIFIED, resource_type="finding",
                resource_id=finding.finding_id, actor=actor,
                summary=(f"Finding {finding.code} on {document.document_ref} marked "
                         f"{new_status} by {actor.email}."),
                before={"status": previous}, after={"status": new_status},
                metadata={"reason": reason[:400], "seeded": True},
            )
            _recompute_risk(db, document, actor)

        elif action == "note":
            investigation = db.execute(
                select(Investigation).where(Investigation.claim_id == claim.id)
                .order_by(Investigation.created_at.desc())
            ).scalars().first()
            if investigation is None:
                investigation = Investigation(
                    id=stable_id("investigation", claim.claim_number),
                    case_number=f"INV-2026-{claim.claim_number[-6:]}", claim_id=claim.id,
                    document_id=documents[0].id,
                    title=f"Manual review of {claim.claim_number}",
                    status=InvestigationStatus.IN_PROGRESS, priority="medium",
                    assigned_to_id=actor.id, opened_by_id=actor.id,
                    opened_at=datetime.now(timezone.utc),
                    risk_score_at_open=claim.risk_score,
                    summary=claim.summary, context={"opened_by": "seed_script"},
                )
                db.add(investigation)
                db.flush()
            investigation.status = InvestigationStatus.IN_PROGRESS
            db.add(InvestigationNote(
                investigation_id=investigation.id, author_id=actor.id, body=target,
                note_type="observation", is_internal=True,
            ))
            audit.record(
                db, action=AuditAction.INVESTIGATION_NOTE_ADDED,
                resource_type="investigation", resource_id=investigation.id, actor=actor,
                summary=f"Note added to {investigation.case_number}.",
                metadata={"seeded": True, "length": len(target or "")},
            )
            applied["notes"] += 1
        db.commit()

    # Close one investigation so the demo includes completed casework.
    closed = db.execute(
        select(Investigation).join(Claim, Claim.id == Investigation.claim_id)
        .where(Claim.claim_number == "CLM-2026-000109")
    ).scalars().first()
    if closed is not None and closed.status != InvestigationStatus.CLOSED:
        investigator = users.get("investigator2@veridoc.example")
        closed.status = InvestigationStatus.CLOSED
        closed.closed_at = datetime.now(timezone.utc)
        closed.resolution = "refer"
        closed.resolution_reason = (
            "Referred to the motor engineering team. The write-off marker and the lost-document "
            "report are both confirmed against the registers; the claim cannot progress until "
            "the claimant supplies an engineer's report and a valid identity document."
        )
        audit.record(
            db, action=AuditAction.INVESTIGATION_UPDATED, resource_type="investigation",
            resource_id=closed.id, actor=investigator,
            summary=f"Investigation {closed.case_number} closed (referred).",
            before={"status": "in_progress"}, after={"status": "closed",
                                                     "resolution": "refer"},
            metadata={"seeded": True},
        )
        db.commit()
    return applied


def _recompute_risk(db: Session, document: Document, actor: User) -> None:
    """Re-run the risk engine after a human decision, exactly as the API does."""
    from app.services.risk import engine as risk_engine

    findings = findings_store.collect(db, document.id)
    inputs = [
        risk_engine.FindingInput(
            code=f.code, category=f.category, severity=f.severity, confidence=f.confidence,
            title=f.title, kind=f.kind, finding_id=f.finding_id, detector=f.detector,
            model_version=f.model_version, status=f.status, page=f.page,
        )
        for f in findings if f.code != "AIGC_NO_SIGNIFICANT_INDICATORS"
    ]
    verification_inputs = findings_store.latest_verification_inputs(db, document.id)
    weights = {r.code: r.weight for r in
               db.execute(select(DetectionRule).where(DetectionRule.enabled.is_(True)))
               .scalars().all()}
    setting = db.execute(
        select(SystemSetting).where(SystemSetting.key == "risk_thresholds")
    ).scalar_one_or_none()
    result = risk_engine.assess(
        inputs, verification_inputs, rule_weights=weights,
        thresholds=setting.value if setting else None,
        stage_coverage={"recomputed_after_review": True},
    )
    for prior in db.execute(
        select(RiskAssessment).where(RiskAssessment.document_id == document.id,
                                     RiskAssessment.is_superseded.is_(False))
    ).scalars().all():
        prior.is_superseded = True
    db.add(RiskAssessment(
        document_id=document.id, claim_id=document.claim_id, score=result.score,
        band=result.band, weights_version=result.weights_version,
        signals=[s.as_dict() for s in result.signals],
        category_scores=result.category_scores, top_reasons=result.top_reasons,
        explanation=result.explanation, interpretation_note=result.interpretation_note,
        coverage={**result.coverage, "mitigations": result.mitigations},
    ))
    document.risk_score, document.risk_band = result.score, result.band
    claim = db.get(Claim, document.claim_id) if document.claim_id else None
    if claim:
        scores = [d.risk_score for d in db.execute(
            select(Document).where(Document.claim_id == claim.id,
                                   Document.deleted_at.is_(None))
        ).scalars().all() if d.risk_score is not None]
        if scores:
            claim.risk_score = max(scores)
            claim.risk_band = risk_engine.band_for_score(
                claim.risk_score, setting.value if setting else None)
    db.flush()


def summary(db: Session) -> dict:
    from sqlalchemy import func

    def count(model):
        return int(db.execute(select(func.count()).select_from(model)).scalar_one())

    findings_total = sum(count(model) for model in findings_store.KIND_MODELS.values())
    return {
        "users": count(User), "roles": count(RoleDefinition), "rules": count(DetectionRule),
        "providers": count(ProviderConfig), "settings": count(SystemSetting),
        "claims": count(Claim), "documents": count(Document), "analysis_runs": count(AnalysisRun),
        "findings": findings_total, "investigations": count(Investigation),
        "audit_entries": count(AuditLog),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VeriDoc database seeding")
    parser.add_argument("--reset", action="store_true",
                        help="drop and recreate the public schema first")
    parser.add_argument("--reference-only", action="store_true",
                        help="seed roles/users/rules/providers/settings only")
    parser.add_argument("--no-analysis", action="store_true",
                        help="create demo documents without running the pipeline")
    parser.add_argument("--no-review", action="store_true",
                        help="skip the scripted human-review history")
    args = parser.parse_args(argv)

    configure_logging()
    if args.reset:
        reset_schema()
    else:
        create_schema()

    with SessionLocal() as db:
        seed_reference(db)
        db.commit()
        if not args.reference_only:
            counters = seed_demo(db, analyse=not args.no_analysis)
            logger.info("demo_seeded", extra=counters)
            if not args.no_analysis and not args.no_review:
                applied = apply_review_script(db)
                logger.info("review_script_applied", extra=applied)
        stats = summary(db)

    print("\nSeeding complete.")
    for key, value in stats.items():
        print(f"  {key:<16} {value}")
    print(f"\n  Sign in with any demo account (password: {settings.seed_password})")
    for spec in DEMO_USERS:
        print(f"    {spec['email']:<34} {spec['role']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
