"""Shared finding contract for every detector.

A detector never concludes fraud. It reports a *signal* with a severity, a
calibrated confidence, the evidence it measured and - where pixels allow - the
region it measured it in.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.db.enums import Severity


@dataclass(slots=True)
class RawFinding:
    code: str
    category: str
    severity: str
    title: str
    description: str
    confidence: float
    detector: str
    model_version: str
    page: int | None = None
    region: dict | None = None
    evidence: dict = field(default_factory=dict)
    recommendation: str | None = None
    extras: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "code": self.code, "category": self.category, "severity": self.severity,
            "title": self.title, "description": self.description,
            "confidence": round(self.confidence, 4), "detector": self.detector,
            "model_version": self.model_version, "page": self.page, "region": self.region,
            "evidence": self.evidence, "recommendation": self.recommendation,
            **self.extras,
        }


@dataclass(slots=True)
class MetadataEntry:
    group: str
    key: str
    value: str | None
    is_anomalous: bool = False
    note: str | None = None
    raw: dict = field(default_factory=dict)


def severity_from_confidence(confidence: float, ceiling: str = Severity.HIGH) -> str:
    """Map a measured confidence onto a severity band, capped per detector class."""
    order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
    if confidence >= 0.85:
        level = Severity.HIGH
    elif confidence >= 0.65:
        level = Severity.MEDIUM
    elif confidence >= 0.45:
        level = Severity.LOW
    else:
        level = Severity.INFO
    return level if order.index(level) <= order.index(ceiling) else ceiling


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def region(x: int, y: int, w: int, h: int, *, unit: str = "render_px", **extra) -> dict:
    out = {"x": int(x), "y": int(y), "width": int(w), "height": int(h), "unit": unit}
    out.update(extra)
    return out
