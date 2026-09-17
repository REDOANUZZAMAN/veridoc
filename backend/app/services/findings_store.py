"""Persistence and unified reading of detector findings.

Findings live in five tables (see ``db/models/findings.py``). This module is the
only place that knows the mapping, and it exposes one uniform read model to the
API, the risk engine and the report generator.

It also implements *review carry-forward*: when a document is re-analysed, a
finding that a human already confirmed or dismissed keeps that decision, so
reprocessing never silently discards human judgement.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import RULES_VERSION
from app.db.enums import FindingCategory, FindingStatus
from app.db.models.findings import (
    AigcFinding,
    ConsistencyFinding,
    CrossDocumentFinding,
    ForensicFinding,
    TamperingFinding,
)
from app.services.forensics.base import RawFinding

KIND_FORENSIC = "forensic"
KIND_AIGC = "aigc"
KIND_TAMPERING = "tampering"
KIND_CONSISTENCY = "consistency"
KIND_CROSS_DOCUMENT = "cross_document"

KIND_MODELS: dict[str, Any] = {
    KIND_FORENSIC: ForensicFinding,
    KIND_AIGC: AigcFinding,
    KIND_TAMPERING: TamperingFinding,
    KIND_CONSISTENCY: ConsistencyFinding,
    KIND_CROSS_DOCUMENT: CrossDocumentFinding,
}

CATEGORY_TO_KIND = {
    FindingCategory.METADATA: KIND_FORENSIC,
    FindingCategory.FORENSICS: KIND_FORENSIC,
    FindingCategory.SECURITY: KIND_FORENSIC,
    FindingCategory.AIGC: KIND_AIGC,
    FindingCategory.TAMPERING: KIND_TAMPERING,
    FindingCategory.CONSISTENCY: KIND_CONSISTENCY,
    FindingCategory.CROSS_DOCUMENT: KIND_CROSS_DOCUMENT,
}

KIND_LABELS = {
    KIND_FORENSIC: "Forensics",
    KIND_AIGC: "Synthetic-media analysis",
    KIND_TAMPERING: "Tampering",
    KIND_CONSISTENCY: "Consistency",
    KIND_CROSS_DOCUMENT: "Cross-document",
}

# Provenance shown in the UI and report so a reader can always tell a model
# output from a deterministic rule from a human decision.
SOURCE_OF_TRUTH = {
    KIND_FORENSIC: "automated_measurement",
    KIND_AIGC: "model_inference",
    KIND_TAMPERING: "automated_correlation",
    KIND_CONSISTENCY: "deterministic_rule",
    KIND_CROSS_DOCUMENT: "deterministic_rule",
}


def kind_for(category: str) -> str:
    return CATEGORY_TO_KIND.get(category, KIND_FORENSIC)


def _region_key(region: dict | None) -> str:
    if not region:
        return "-"
    return ":".join(str(int(region.get(k, 0)) // 24) for k in ("x", "y", "width", "height"))


def review_key(kind: str, code: str, page: int | None, region: dict | None) -> str:
    return f"{kind}|{code}|{page or 0}|{_region_key(region)}"


def snapshot_review_state(db: Session, document_id: str) -> dict[str, dict]:
    """Capture human decisions before findings are regenerated."""
    out: dict[str, dict] = {}
    for kind, model in KIND_MODELS.items():
        rows = db.execute(
            select(model).where(model.document_id == document_id)
        ).scalars().all()
        for row in rows:
            if row.status == FindingStatus.OPEN:
                continue
            out[review_key(kind, row.finding_code, row.page, row.region)] = {
                "status": row.status,
                "review_reason": row.review_reason,
                "reviewed_by_id": row.reviewed_by_id,
            }
    return out


def clear_findings(db: Session, document_id: str, *, kinds: Iterable[str] | None = None) -> int:
    removed = 0
    for kind in kinds or KIND_MODELS:
        model = KIND_MODELS[kind]
        rows = db.execute(select(model).where(model.document_id == document_id)).scalars().all()
        for row in rows:
            db.delete(row)
            removed += 1
    db.flush()
    return removed


def persist(
    db: Session,
    findings: list[RawFinding],
    *,
    document_id: str,
    claim_id: str | None,
    analysis_run_id: str | None,
    review_state: dict[str, dict] | None = None,
    extra: dict | None = None,
) -> list[Any]:
    created: list[Any] = []
    for raw in findings:
        kind = kind_for(raw.category)
        model = KIND_MODELS[kind]
        common = {
            "finding_code": raw.code,
            "category": raw.category,
            "severity": raw.severity,
            "title": raw.title[:200],
            "description": raw.description[:2000],
            "detector": raw.detector[:80],
            "model_version": raw.model_version[:40],
            "confidence": float(raw.confidence),
            "page": raw.page,
            "region": raw.region,
            "evidence": raw.evidence,
            "recommendation": (raw.recommendation or None),
            "rule_version": raw.extras.get("rule_version", RULES_VERSION),
            "analysis_run_id": analysis_run_id,
            "status": FindingStatus.OPEN,
        }
        if kind == KIND_CROSS_DOCUMENT:
            common["claim_id"] = raw.extras.get("claim_id") or claim_id
            common["document_id"] = raw.extras.get("document_id") or document_id
            common["counterpart_document_id"] = raw.extras.get("counterpart_document_id")
            common["field_key"] = raw.extras.get("field_key", "unknown")
            common["value_a"] = raw.extras.get("value_a")
            common["value_b"] = raw.extras.get("value_b")
            common["similarity"] = raw.extras.get("similarity")
        else:
            common["document_id"] = document_id

        if kind == KIND_FORENSIC:
            common["signal_group"] = raw.extras.get("signal_group", "structure")
        elif kind == KIND_AIGC:
            common["provider_key"] = raw.extras.get("provider_key", "unknown")
            common["provider_label"] = raw.extras.get("provider_label", "unknown")
            common["is_demo_provider"] = bool(raw.extras.get("is_demo_provider", True))
            common["indicator_scores"] = raw.extras.get("indicator_scores", {})
            common["likelihood_band"] = raw.extras.get("likelihood_band", "inconclusive")
        elif kind == KIND_TAMPERING:
            common["tamper_type"] = raw.extras.get("tamper_type", "region_anomaly")
            common["affected_field"] = raw.extras.get("affected_field")
            common["affected_value"] = (raw.extras.get("affected_value") or None)
            common["overlay_key"] = raw.extras.get("overlay_key")
        elif kind == KIND_CONSISTENCY:
            common["rule_code"] = raw.extras.get("rule_code", raw.code)
            common["fields_involved"] = raw.extras.get("fields_involved", [])
            common["expected"] = raw.extras.get("expected")
            common["actual"] = raw.extras.get("actual")

        prior = (review_state or {}).get(
            review_key(kind, raw.code, raw.page, raw.region)
        )
        if prior:
            common["status"] = prior["status"]
            common["review_reason"] = prior["review_reason"]
            common["reviewed_by_id"] = prior["reviewed_by_id"]

        row = model(**{**common, **(extra or {})})
        db.add(row)
        created.append(row)
    db.flush()
    return created


@dataclass(slots=True)
class UnifiedFinding:
    finding_id: str
    kind: str
    category: str
    code: str
    severity: str
    confidence: float
    title: str
    description: str
    detector: str
    model_version: str
    status: str
    page: int | None
    region: dict | None
    evidence: dict
    recommendation: str | None
    created_at: Any
    review_reason: str | None = None
    reviewed_by_id: str | None = None
    extra: dict | None = None

    def as_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "kind": self.kind,
            "kind_label": KIND_LABELS.get(self.kind, self.kind),
            "category": self.category,
            "code": self.code,
            "severity": self.severity,
            "confidence": round(self.confidence, 4),
            "title": self.title,
            "description": self.description,
            "detector": self.detector,
            "model_version": self.model_version,
            "status": self.status,
            "page": self.page,
            "region": self.region,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "review_reason": self.review_reason,
            "reviewed_by_id": self.reviewed_by_id,
            "provenance": SOURCE_OF_TRUTH.get(self.kind, "automated_measurement"),
            **(self.extra or {}),
        }


def _to_unified(kind: str, row) -> UnifiedFinding:
    extra: dict = {}
    if kind == KIND_TAMPERING:
        extra = {"tamper_type": row.tamper_type, "affected_field": row.affected_field,
                 "affected_value": row.affected_value, "overlay_key": row.overlay_key}
    elif kind == KIND_AIGC:
        extra = {"provider_key": row.provider_key, "provider_label": row.provider_label,
                 "is_demo_provider": row.is_demo_provider,
                 "likelihood_band": row.likelihood_band,
                 "indicator_scores": row.indicator_scores}
    elif kind == KIND_CONSISTENCY:
        extra = {"rule_code": row.rule_code, "fields_involved": row.fields_involved,
                 "expected": row.expected, "actual": row.actual}
    elif kind == KIND_CROSS_DOCUMENT:
        extra = {"field_key": row.field_key, "value_a": row.value_a, "value_b": row.value_b,
                 "similarity": row.similarity,
                 "counterpart_document_id": row.counterpart_document_id,
                 "claim_id": row.claim_id}
    elif kind == KIND_FORENSIC:
        extra = {"signal_group": row.signal_group}
    return UnifiedFinding(
        finding_id=row.id, kind=kind, category=row.category, code=row.finding_code,
        severity=row.severity, confidence=row.confidence, title=row.title,
        description=row.description, detector=row.detector, model_version=row.model_version,
        status=row.status, page=row.page, region=row.region, evidence=row.evidence or {},
        recommendation=row.recommendation, created_at=row.created_at,
        review_reason=row.review_reason, reviewed_by_id=row.reviewed_by_id, extra=extra,
    )


def collect(db: Session, document_id: str, *, kinds: Iterable[str] | None = None) -> list[UnifiedFinding]:
    out: list[UnifiedFinding] = []
    for kind in kinds or KIND_MODELS:
        model = KIND_MODELS[kind]
        rows = db.execute(
            select(model).where(model.document_id == document_id)
            .order_by(model.created_at.asc())
        ).scalars().all()
        out.extend(_to_unified(kind, row) for row in rows)
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    out.sort(key=lambda f: (severity_rank.get(f.severity, 9), -f.confidence))
    return out


def collect_for_claim(db: Session, claim_id: str) -> list[UnifiedFinding]:
    from app.db.models.document import Document

    doc_ids = db.execute(
        select(Document.id).where(Document.claim_id == claim_id,
                                  Document.deleted_at.is_(None))
    ).scalars().all()
    out: list[UnifiedFinding] = []
    for doc_id in doc_ids:
        out.extend(collect(db, doc_id))
    return out


def find_by_id(db: Session, kind: str, finding_id: str):
    model = KIND_MODELS.get(kind)
    if model is None:
        return None
    return db.execute(select(model).where(model.id == finding_id)).scalar_one_or_none()


def locate_finding(db: Session, finding_id: str) -> tuple[str, Any] | tuple[None, None]:
    for kind, model in KIND_MODELS.items():
        row = db.execute(select(model).where(model.id == finding_id)).scalar_one_or_none()
        if row is not None:
            return kind, row
    return None, None


def latest_verification_inputs(db: Session, document_id: str) -> list:
    """Most recent result per verification request type.

    A document accumulates verification requests over time - the pipeline runs
    them, and an investigator may re-run a check after asking the issuer for a
    correction. Only the latest answer per check type is a live signal; feeding
    every historic attempt into the risk engine would count the same
    disagreement several times over.
    """
    from app.db.models.verification import VerificationRequest
    from app.services.risk import engine as risk_engine

    rows = db.execute(
        select(VerificationRequest)
        .where(VerificationRequest.document_id == document_id)
        .order_by(VerificationRequest.created_at.desc())
    ).scalars().all()

    seen: set[str] = set()
    inputs = []
    for request in rows:
        if request.request_type in seen or not request.result:
            continue
        seen.add(request.request_type)
        inputs.append(risk_engine.VerificationInput(
            provider_key=request.provider_key, provider_label=request.provider_label,
            request_type=request.request_type, outcome=request.result.outcome,
            summary=request.result.summary,
            failed_checks=[c.get("label") for c in (request.result.checks or [])
                           if c.get("passed") is False],
            is_demo_data=request.result.is_demo_data, request_id=request.id,
        ))
    return inputs
