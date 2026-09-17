"""AI-generated / AI-edited content analysis abstraction.

Design rules baked into the types below:

1. The output is a **likelihood band**, never a verdict. There is no code path
   that can emit "definitely AI" or "100% fake".
2. Every provider must declare ``model_name`` and ``model_version``; both are
   persisted on the finding and printed in the report.
3. A provider that is unavailable raises ``ProviderUnavailable``; the pipeline
   records the stage as degraded rather than inventing a score.
4. A provider that does not run a trained model must set ``is_demo = True`` and
   supply a ``disclaimer`` that is surfaced in the UI and the report.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

BAND_NONE = "no_significant_indicators"
BAND_WEAK = "weak_indicators"
BAND_POSSIBLE = "possible_indicators"
BAND_NOTABLE = "notable_indicators"

BAND_LABELS = {
    BAND_NONE: "No significant synthetic-media indicators detected",
    BAND_WEAK: "Weak synthetic-media indicators present",
    BAND_POSSIBLE: "Potential synthetic-media indicators detected",
    BAND_NOTABLE: "Notable synthetic-media indicators detected",
}

BAND_THRESHOLDS = ((0.68, BAND_NOTABLE), (0.50, BAND_POSSIBLE), (0.35, BAND_WEAK))

UNCERTAINTY_NOTE = (
    "Synthetic-media analysis is probabilistic. A raised likelihood is an "
    "investigative lead that must be corroborated by metadata, provenance or "
    "issuer verification; a low likelihood does not certify that content is "
    "camera-original."
)


def band_for(likelihood: float) -> str:
    for threshold, band in BAND_THRESHOLDS:
        if likelihood >= threshold:
            return band
    return BAND_NONE


@dataclass(slots=True)
class AigcIndicator:
    key: str
    label: str
    measured: float
    normalized: float
    weight: float
    note: str

    @property
    def contribution(self) -> float:
        return self.normalized * self.weight

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "measured": round(self.measured, 5),
            "normalized": round(self.normalized, 4), "weight": self.weight,
            "contribution": round(self.contribution, 4), "note": self.note,
        }


@dataclass(slots=True)
class AigcTarget:
    page_number: int
    image_bytes: bytes
    is_lossless_render: bool = False
    source_mime: str = "image/png"
    has_camera_exif: bool = False
    exif_summary: dict = field(default_factory=dict)
    ocr_confidences: list[float] = field(default_factory=list)
    glyph_heights: list[float] = field(default_factory=list)
    document_type: str | None = None


@dataclass(slots=True)
class AigcPageResult:
    page_number: int
    likelihood: float
    band: str
    indicators: list[AigcIndicator]
    provider_key: str
    provider_label: str
    model_name: str
    model_version: str
    is_demo: bool
    disclaimer: str
    summary: str
    evidence: dict = field(default_factory=dict)
    region_hints: list[dict] = field(default_factory=list)

    @property
    def band_label(self) -> str:
        return BAND_LABELS[self.band]

    def as_dict(self) -> dict:
        return {
            "page": self.page_number,
            "likelihood": round(self.likelihood, 4),
            "band": self.band,
            "band_label": self.band_label,
            "indicators": [i.as_dict() for i in self.indicators],
            "provider": {
                "key": self.provider_key, "label": self.provider_label,
                "model_name": self.model_name, "model_version": self.model_version,
                "is_demo": self.is_demo,
            },
            "disclaimer": self.disclaimer,
            "uncertainty_note": UNCERTAINTY_NOTE,
            "summary": self.summary,
            "evidence": self.evidence,
            "region_hints": self.region_hints,
        }


class AigcProvider(ABC):
    key: str = "abstract"
    label: str = "Abstract AIGC provider"
    model_name: str = "abstract"
    model_version: str = "0"
    is_demo: bool = True
    disclaimer: str = ""

    def available(self) -> tuple[bool, str]:
        return True, "ready"

    @abstractmethod
    def analyze(self, target: AigcTarget) -> AigcPageResult: ...

    def describe(self) -> dict:
        ok, detail = self.available()
        return {
            "key": self.key, "label": self.label, "model_name": self.model_name,
            "model_version": self.model_version, "is_demo": self.is_demo,
            "available": ok, "detail": detail, "disclaimer": self.disclaimer,
        }
