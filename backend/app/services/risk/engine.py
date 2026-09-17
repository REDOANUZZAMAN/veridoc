"""Fraud risk engine.

Transparent by construction. The score is a deterministic function of the
signals, and every step is returned alongside it:

    contribution(signal) = weight(code) x confidence x severity_multiplier
    category_score       = cap x (1 - exp(-sum(contributions) / cap))
    score                = round(100 x sum(category_scores) / CALIBRATION)

The per-category saturation is what stops twelve weak metadata signals from
outweighing one confirmed cross-document mismatch, and it keeps the score
monotone in every input.

**What the score is not.** It is not a probability that fraud occurred. It is a
triage ranking that decides how much human attention a document gets. The bands
are worded accordingly: Low Concern / Review Recommended / High Concern.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import exp

from app.core.config import RISK_WEIGHTS_VERSION
from app.db.enums import (
    RISK_BAND_LABELS,
    FindingCategory,
    FindingStatus,
    RiskBand,
    Severity,
    VerificationOutcome,
)

SEVERITY_MULTIPLIER = {
    Severity.INFO: 0.35,
    Severity.LOW: 0.60,
    Severity.MEDIUM: 1.00,
    Severity.HIGH: 1.35,
    Severity.CRITICAL: 1.60,
}

# Per-category ceilings. Their purpose is to stop a crowd of weak signals in one
# category from outweighing a single decisive one elsewhere - not to stop a
# genuinely decisive category from reaching High Concern on its own. External
# verification therefore has the highest ceiling: when the issuer's own record
# contradicts the document, that is the strongest evidence this platform can
# obtain. Synthetic-media analysis has the lowest, because the bundled provider
# is a heuristic rather than a calibrated model.
CATEGORY_CAPS: dict[str, float] = {
    FindingCategory.VERIFICATION: 70.0,
    FindingCategory.TAMPERING: 58.0,
    FindingCategory.CONSISTENCY: 50.0,
    FindingCategory.CROSS_DOCUMENT: 50.0,
    FindingCategory.SECURITY: 40.0,
    FindingCategory.FORENSICS: 34.0,
    FindingCategory.METADATA: 24.0,
    FindingCategory.AIGC: 20.0,
}

CATEGORY_LABELS = {
    FindingCategory.VERIFICATION: "External verification",
    FindingCategory.TAMPERING: "Tampering indicators",
    FindingCategory.CONSISTENCY: "Internal consistency",
    FindingCategory.CROSS_DOCUMENT: "Cross-document agreement",
    FindingCategory.FORENSICS: "Document forensics",
    FindingCategory.SECURITY: "File security",
    FindingCategory.METADATA: "Metadata provenance",
    FindingCategory.AIGC: "Synthetic-media indicators",
}

# Fallback weight when a finding code has no entry in detection_rules.
DEFAULT_CATEGORY_WEIGHT: dict[str, float] = {
    FindingCategory.VERIFICATION: 26.0,
    FindingCategory.TAMPERING: 22.0,
    FindingCategory.CONSISTENCY: 14.0,
    FindingCategory.CROSS_DOCUMENT: 20.0,
    FindingCategory.FORENSICS: 11.0,
    FindingCategory.SECURITY: 18.0,
    FindingCategory.METADATA: 10.0,
    FindingCategory.AIGC: 12.0,
}

# Saturation steepness and the scale factor that turns the aggregate into a
# 0-100 ranking. Both were fitted against the bundled corpus so that a clean
# document scores near zero, one substantiated anomaly lands in Review
# Recommended, and corroborating anomalies across categories reach High Concern.
SATURATION_K = 1.3
CALIBRATION = 72.0
MAX_MITIGATION = 6.0

DEFAULT_THRESHOLDS = {"review_recommended": 40, "high_concern": 75}

INTERPRETATION_NOTE = (
    "This score is a triage ranking that determines how much human attention the document "
    "receives. It is not a probability that fraud occurred, and no combination of signals in "
    "this platform can establish that a document is fake. Confirmed findings and external "
    "verification mismatches are leads for an investigator; the final decision on the claim is "
    "always recorded by a named human reviewer."
)


@dataclass(slots=True)
class RiskSignal:
    code: str
    label: str
    category: str
    severity: str
    confidence: float
    weight: float
    contribution: float
    source: str
    detector: str | None = None
    model_version: str | None = None
    finding_kind: str | None = None
    finding_id: str | None = None
    human_confirmed: bool = False
    page: int | None = None

    def as_dict(self) -> dict:
        return {
            "code": self.code, "label": self.label, "category": self.category,
            "category_label": CATEGORY_LABELS.get(self.category, self.category),
            "severity": self.severity, "confidence": round(self.confidence, 4),
            "weight": round(self.weight, 2), "contribution": round(self.contribution, 3),
            "source": self.source, "detector": self.detector,
            "model_version": self.model_version, "finding_kind": self.finding_kind,
            "finding_id": self.finding_id, "human_confirmed": self.human_confirmed,
            "page": self.page,
        }


@dataclass(slots=True)
class RiskResult:
    score: int
    band: str
    band_label: str
    signals: list[RiskSignal]
    category_scores: dict[str, dict]
    top_reasons: list[dict]
    explanation: str
    coverage: dict
    mitigations: list[dict] = field(default_factory=list)
    weights_version: str = RISK_WEIGHTS_VERSION
    interpretation_note: str = INTERPRETATION_NOTE
    dismissed_count: int = 0

    def as_dict(self) -> dict:
        return {
            "score": self.score, "band": self.band, "band_label": self.band_label,
            "signals": [s.as_dict() for s in self.signals],
            "category_scores": self.category_scores, "top_reasons": self.top_reasons,
            "explanation": self.explanation, "coverage": self.coverage,
            "mitigations": self.mitigations, "weights_version": self.weights_version,
            "interpretation_note": self.interpretation_note,
            "dismissed_signals_excluded": self.dismissed_count,
            "formula": ("contribution = weight x confidence x severity_multiplier; "
                        f"category_score = cap x (1 - exp(-{SATURATION_K} x sum / cap)); "
                        f"score = round(100 x sum(category_scores) / {CALIBRATION})"),
            "thresholds": self.coverage.get("thresholds", DEFAULT_THRESHOLDS),
        }


@dataclass(slots=True)
class FindingInput:
    code: str
    category: str
    severity: str
    confidence: float
    title: str
    kind: str
    finding_id: str | None = None
    detector: str | None = None
    model_version: str | None = None
    status: str = FindingStatus.OPEN
    page: int | None = None


@dataclass(slots=True)
class VerificationInput:
    provider_key: str
    provider_label: str
    request_type: str
    outcome: str
    summary: str
    failed_checks: list[str] = field(default_factory=list)
    is_demo_data: bool = True
    request_id: str | None = None


def band_for_score(score: int, thresholds: dict | None = None) -> str:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if score >= int(t["high_concern"]):
        return RiskBand.HIGH_CONCERN
    if score >= int(t["review_recommended"]):
        return RiskBand.REVIEW_RECOMMENDED
    return RiskBand.LOW_CONCERN


def _weight_for(code: str, category: str, rule_weights: dict[str, float] | None) -> float:
    if rule_weights and code in rule_weights:
        return float(rule_weights[code])
    return DEFAULT_CATEGORY_WEIGHT.get(category, 10.0)


def assess(
    findings: list[FindingInput],
    verifications: list[VerificationInput] | None = None,
    *,
    rule_weights: dict[str, float] | None = None,
    thresholds: dict | None = None,
    stage_coverage: dict | None = None,
) -> RiskResult:
    verifications = verifications or []
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    signals: list[RiskSignal] = []
    dismissed = 0

    for f in findings:
        if f.status == FindingStatus.DISMISSED:
            # A reviewer dismissed this signal with a recorded reason: it stops
            # contributing to the score, and the exclusion is reported.
            dismissed += 1
            continue
        confidence = f.confidence
        human_confirmed = f.status == FindingStatus.CONFIRMED
        if human_confirmed:
            confidence = max(confidence, 0.95)
        weight = _weight_for(f.code, f.category, rule_weights)
        multiplier = SEVERITY_MULTIPLIER.get(f.severity, 1.0)
        signals.append(RiskSignal(
            code=f.code, label=f.title, category=f.category, severity=f.severity,
            confidence=confidence, weight=weight,
            contribution=weight * confidence * multiplier,
            source="human_confirmed_finding" if human_confirmed else "automated_finding",
            detector=f.detector, model_version=f.model_version, finding_kind=f.kind,
            finding_id=f.finding_id, human_confirmed=human_confirmed, page=f.page,
        ))

    mitigations: list[dict] = []
    for v in verifications:
        if v.outcome in {VerificationOutcome.MISMATCH, VerificationOutcome.PARTIAL_MATCH}:
            severity = (Severity.HIGH if v.outcome == VerificationOutcome.MISMATCH
                        else Severity.MEDIUM)
            confidence = 0.91 if v.outcome == VerificationOutcome.MISMATCH else 0.7
            code = f"VERIFY_{v.request_type.upper()}_{v.outcome.upper()}"
            weight = _weight_for(code, FindingCategory.VERIFICATION, rule_weights)
            signals.append(RiskSignal(
                code=code,
                label=(f"{v.provider_label}: {v.outcome.replace('_', ' ')}"
                       + (f" ({', '.join(v.failed_checks[:3])})" if v.failed_checks else "")),
                category=FindingCategory.VERIFICATION, severity=severity, confidence=confidence,
                weight=weight,
                contribution=weight * confidence * SEVERITY_MULTIPLIER[severity],
                source="demo_verification" if v.is_demo_data else "external_verification",
                detector=v.provider_key, model_version=None,
                finding_kind="verification", finding_id=v.request_id,
            ))
        elif v.outcome == VerificationOutcome.NOT_FOUND:
            code = f"VERIFY_{v.request_type.upper()}_NOT_FOUND"
            weight = _weight_for(code, FindingCategory.VERIFICATION, rule_weights)
            signals.append(RiskSignal(
                code=code, label=f"{v.provider_label}: reference not found",
                category=FindingCategory.VERIFICATION, severity=Severity.HIGH, confidence=0.8,
                weight=weight, contribution=weight * 0.8 * SEVERITY_MULTIPLIER[Severity.HIGH],
                source="demo_verification" if v.is_demo_data else "external_verification",
                detector=v.provider_key, finding_kind="verification", finding_id=v.request_id,
            ))
        elif v.outcome == VerificationOutcome.MATCH:
            mitigations.append({
                "code": f"VERIFY_{v.request_type.upper()}_MATCH",
                "label": f"{v.provider_label}: all checks agree",
                "value": 2.0, "is_demo_data": v.is_demo_data,
                "note": ("Corroborating evidence. Applied only when no high or critical finding "
                         "is present, and capped overall."),
            })

    # --- aggregate -------------------------------------------------------------
    category_totals: dict[str, float] = {}
    for s in signals:
        category_totals[s.category] = category_totals.get(s.category, 0.0) + s.contribution

    category_scores: dict[str, dict] = {}
    aggregate = 0.0
    for category, raw in category_totals.items():
        cap = CATEGORY_CAPS.get(category, 20.0)
        saturated = cap * (1.0 - exp(-SATURATION_K * raw / cap))
        aggregate += saturated
        category_scores[category] = {
            "label": CATEGORY_LABELS.get(category, category),
            "raw_contribution": round(raw, 3),
            "cap": cap,
            "saturated_score": round(saturated, 3),
            "signal_count": sum(1 for s in signals if s.category == category),
        }

    has_severe = any(s.severity in {Severity.HIGH, Severity.CRITICAL} for s in signals)
    applied_mitigation = 0.0
    if mitigations and not has_severe:
        applied_mitigation = min(MAX_MITIGATION, sum(m["value"] for m in mitigations))
    for m in mitigations:
        m["applied"] = applied_mitigation > 0
        m["suppressed_reason"] = (
            "A high or critical finding is present, so corroboration does not reduce the score."
            if has_severe else None
        )

    score_float = max(0.0, (aggregate * 100.0 / CALIBRATION) - applied_mitigation)
    score = int(min(100, round(score_float)))
    band = band_for_score(score, thresholds)

    ranked = sorted(signals, key=lambda s: -s.contribution)
    top_reasons = [
        {
            "code": s.code, "label": s.label,
            "category": CATEGORY_LABELS.get(s.category, s.category),
            "severity": s.severity, "confidence": round(s.confidence, 3),
            "contribution": round(s.contribution, 2), "source": s.source,
            "finding_kind": s.finding_kind, "finding_id": s.finding_id, "page": s.page,
        }
        for s in ranked[:6]
    ]

    coverage = dict(stage_coverage or {})
    coverage["thresholds"] = thresholds
    coverage["signal_count"] = len(signals)
    coverage["categories_contributing"] = sorted(category_totals)

    return RiskResult(
        score=score, band=band, band_label=RISK_BAND_LABELS[band], signals=signals,
        category_scores=category_scores, top_reasons=top_reasons,
        explanation=_explain(score, band, top_reasons, coverage, dismissed, applied_mitigation),
        coverage=coverage, mitigations=mitigations, dismissed_count=dismissed,
    )


def _explain(
    score: int, band: str, top_reasons: list[dict], coverage: dict, dismissed: int,
    mitigation: float,
) -> str:
    label = RISK_BAND_LABELS[band]
    if not top_reasons:
        base = (f"{label} ({score}/100). No contributing signals were raised by the analysis "
                "stages that completed.")
    else:
        bullets = "; ".join(
            f"{r['label']} ({r['category'].lower()}, {r['severity']}, "
            f"confidence {r['confidence']:.2f}, contribution {r['contribution']:.1f})"
            for r in top_reasons[:4]
        )
        base = f"{label} ({score}/100). Principal contributors: {bullets}."
    degraded = coverage.get("degraded_stages") or []
    if degraded:
        base += (f" Note: {len(degraded)} analysis stage(s) did not complete "
                 f"({', '.join(degraded)}), so this assessment is based on partial coverage and "
                 "the absence of findings in those areas is not evidence of their absence.")
    if dismissed:
        base += (f" {dismissed} finding(s) dismissed by a reviewer were excluded from the score.")
    if mitigation:
        base += (f" A corroboration credit of {mitigation:.1f} point(s) was applied for external "
                 "verification agreement.")
    return base


def weight_catalogue() -> list[dict]:
    """Default weights, for the admin Rules screen."""
    return [
        {"category": category, "label": CATEGORY_LABELS[category],
         "default_weight": weight, "cap": CATEGORY_CAPS[category]}
        for category, weight in DEFAULT_CATEGORY_WEIGHT.items()
    ]
