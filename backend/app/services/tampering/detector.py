"""Tampering detection - correlation layer over the raw forensic signals.

A single forensic metric is noisy. This module fuses spatially overlapping
signals from independent detectors (ELA, noise residual, copy-move, local
compression quality, typography, exact PDF font data) into one region-level
assessment, then names *what* sits inside that region by intersecting it with
the extracted fields.

That is how "Region: Amount $8,500 - potentially edited region, confidence 82%"
is produced: the region comes from measurement, the label comes from extraction.

A tampering finding is an investigative signal. It is never proof of fraud and
the wording never claims otherwise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.db.enums import FindingCategory, Severity
from app.services.extract.engine import FieldValue, LineItem
from app.services.forensics.base import (
    RawFinding,
    clamp,
    region,
    severity_from_confidence,
)

DETECTOR = "tampering-correlation-engine"
DETECTOR_VERSION = "1.5.0"

# How much each upstream signal is trusted on its own.
SOURCE_RELIABILITY: dict[str, float] = {
    "pdf_font_mix": 0.90,
    "copy_move": 0.85,
    "ela": 0.72,
    "local_quality": 0.70,
    "txt_stroke_weight_anomaly": 0.66,
    "noise": 0.60,
    "txt_baseline_anomaly": 0.58,
    "txt_glyph_size_anomaly": 0.54,
    "txt_low_confidence_island": 0.48,
    "pdf_annotation": 0.75,
    "embedded_image_mismatch": 0.68,
}
STRONG_SOURCES = {"pdf_font_mix", "copy_move", "pdf_annotation"}

SIGNATURE_TERMS = re.compile(
    r"\b(signature|signed|sign here|authorised|authorized|for and on behalf|stamp|seal|"
    r"official seal|verified by)\b", re.I
)

FIELD_TAMPER_TYPES = {
    "money": ("edited_amount", "Potentially edited amount"),
    "date": ("modified_date", "Potentially modified date"),
    "identifier": ("altered_identifier", "Potentially altered reference number"),
    "string": ("replaced_text", "Potentially replaced text"),
    "number": ("edited_value", "Potentially edited value"),
    "percent": ("edited_value", "Potentially edited value"),
}
PARTY_GROUPS = {"party", "identity", "provider"}


@dataclass(slots=True)
class CompositeRegion:
    page: int
    box: dict
    sources: dict[str, float] = field(default_factory=dict)
    texts: list[str] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)

    @property
    def combined_confidence(self) -> float:
        """Noisy-OR over independent detectors, each damped by its reliability."""
        product = 1.0
        for source, conf in self.sources.items():
            reliability = SOURCE_RELIABILITY.get(source, 0.5)
            product *= 1.0 - clamp(conf * reliability, 0.0, 0.95)
        return clamp(1.0 - product, 0.0, 0.93)

    @property
    def has_strong_source(self) -> bool:
        return bool(set(self.sources) & STRONG_SOURCES)


def _iou(a: dict, b: dict) -> float:
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    ix = max(0, min(ax2, bx2) - max(a["x"], b["x"]))
    iy = max(0, min(ay2, by2) - max(a["y"], b["y"]))
    inter = ix * iy
    if inter == 0:
        return 0.0
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / max(union, 1)


def _overlaps(a: dict, b: dict, *, slack: int = 12) -> bool:
    ax2, ay2 = a["x"] + a["width"] + slack, a["y"] + a["height"] + slack
    bx2, by2 = b["x"] + b["width"] + slack, b["y"] + b["height"] + slack
    return not (ax2 < b["x"] or bx2 < a["x"] or ay2 < b["y"] or by2 < a["y"])


def _merge_box(a: dict, b: dict) -> dict:
    x = min(a["x"], b["x"])
    y = min(a["y"], b["y"])
    x2 = max(a["x"] + a["width"], b["x"] + b["width"])
    y2 = max(a["y"] + a["height"], b["y"] + b["height"])
    return region(x, y, x2 - x, y2 - y)


def merge_regions(raw_regions: list[dict]) -> list[CompositeRegion]:
    composites: list[CompositeRegion] = []
    for item in raw_regions:
        box = item.get("region")
        if not box or box.get("width", 0) <= 0:
            continue
        page = int(item.get("page") or 1)
        source = str(item.get("source", "unknown"))
        conf = float(item.get("confidence", 0.5))
        placed = False
        for comp in composites:
            if comp.page == page and _overlaps(comp.box, box):
                comp.box = _merge_box(comp.box, box)
                comp.sources[source] = max(comp.sources.get(source, 0.0), conf)
                if item.get("text"):
                    comp.texts.append(str(item["text"]))
                comp.details.append({"source": source, "confidence": round(conf, 4),
                                     "region": box})
                placed = True
                break
        if not placed:
            composites.append(CompositeRegion(
                page=page, box=dict(box), sources={source: conf},
                texts=[str(item["text"])] if item.get("text") else [],
                details=[{"source": source, "confidence": round(conf, 4), "region": box}],
            ))
    # A second pass catches regions that only became adjacent after merging.
    changed = True
    while changed:
        changed = False
        for i in range(len(composites)):
            for j in range(i + 1, len(composites)):
                a, b = composites[i], composites[j]
                if a.page == b.page and _overlaps(a.box, b.box, slack=6):
                    a.box = _merge_box(a.box, b.box)
                    for source, conf in b.sources.items():
                        a.sources[source] = max(a.sources.get(source, 0.0), conf)
                    a.texts.extend(b.texts)
                    a.details.extend(b.details)
                    composites.pop(j)
                    changed = True
                    break
            if changed:
                break
    composites.sort(key=lambda c: -c.combined_confidence)
    return composites


def _field_at(box: dict, page: int, fields: list[FieldValue]) -> FieldValue | None:
    best: tuple[float, FieldValue] | None = None
    for f in fields:
        if f.page != page or not f.bbox:
            continue
        score = _iou(box, f.bbox)
        if score <= 0 and not _overlaps(box, f.bbox, slack=6):
            continue
        score = max(score, 0.01)
        if best is None or score > best[0]:
            best = (score, f)
    return best[1] if best else None


def _line_item_at(box: dict, page: int, items: list[LineItem]) -> LineItem | None:
    for item in items:
        if item.page == page or item.bbox is None:
            if item.bbox and _overlaps(box, item.bbox, slack=4):
                return item
    return None


def detect_tampering(
    *,
    suspect_regions: list[dict],
    fields: list[FieldValue],
    line_items: list[LineItem],
    page_texts: dict[int, str] | None = None,
    page_sizes: dict[int, tuple[int, int]] | None = None,
    embedded_image_conflicts: list[dict] | None = None,
) -> tuple[list[RawFinding], list[dict]]:
    """Returns (findings, composite_region_dicts)."""
    regions_in = list(suspect_regions)
    for conflict in embedded_image_conflicts or []:
        if conflict.get("region"):
            regions_in.append({
                "source": "embedded_image_mismatch", "region": conflict["region"],
                "page": conflict.get("page", 1), "confidence": conflict.get("confidence", 0.6),
            })

    composites = merge_regions(regions_in)
    page_texts = page_texts or {}
    page_sizes = page_sizes or {}
    findings: list[RawFinding] = []
    exported: list[dict] = []

    for comp in composites:
        confidence = comp.combined_confidence
        distinct_sources = len(comp.sources)
        # Guard against single weak signals becoming "tampering".
        if not comp.has_strong_source and distinct_sources < 2:
            continue
        if confidence < 0.45:
            continue

        field_hit = _field_at(comp.box, comp.page, fields)
        item_hit = None if field_hit else _line_item_at(comp.box, comp.page, line_items)
        tamper_type, title = _classify(comp, field_hit, page_texts.get(comp.page, ""),
                                       page_sizes.get(comp.page))
        affected_field = field_hit.key if field_hit else (
            f"line_item_{item_hit.index}" if item_hit else None
        )
        affected_value = None
        if field_hit:
            affected_value = (field_hit.value_normalized or field_hit.value_raw)[:200]
        elif item_hit:
            affected_value = f"{item_hit.description} = {item_hit.amount}"

        subject = (
            f"{field_hit.label}: {affected_value}" if field_hit
            else (f"line item “{item_hit.description}”" if item_hit
                  else f"region at ({comp.box['x']},{comp.box['y']})")
        )
        sources_text = ", ".join(sorted(comp.sources))
        description = (
            f"{distinct_sources} independent detector(s) flagged the same area of page "
            f"{comp.page} ({sources_text}). The area covers {subject}. Overlapping, "
            "independently measured anomalies in one spot are the pattern left by a localised "
            "edit - but legitimate causes exist for each individual signal, so this is an "
            "investigative lead requiring confirmation, not evidence of fraud."
        )
        severity = severity_from_confidence(
            confidence, Severity.HIGH if (field_hit or item_hit) else Severity.MEDIUM
        )
        findings.append(RawFinding(
            code=f"TAMPER_{tamper_type.upper()}", category=FindingCategory.TAMPERING,
            severity=severity,
            title=f"{title} on page {comp.page}"
                  + (f" - {field_hit.label}" if field_hit else ""),
            description=description, confidence=confidence, detector=DETECTOR,
            model_version=DETECTOR_VERSION, page=comp.page, region=comp.box,
            evidence={
                "contributing_signals": comp.details,
                "distinct_detectors": distinct_sources,
                "source_reliability": {s: SOURCE_RELIABILITY.get(s, 0.5) for s in comp.sources},
                "combination": "noisy_or_over_independent_detectors",
                "tokens_in_region": comp.texts[:8],
                "affected_field": affected_field,
                "affected_value": affected_value,
            },
            recommendation=(
                "Verify this value directly with the issuing organisation before relying on it."
                if field_hit else
                "Inspect the highlighted region against the original document."
            ),
            extras={"tamper_type": tamper_type, "affected_field": affected_field,
                    "affected_value": affected_value},
        ))
        exported.append({
            "page": comp.page, "region": comp.box, "confidence": round(confidence, 4),
            "sources": {k: round(v, 4) for k, v in comp.sources.items()},
            "tamper_type": tamper_type, "affected_field": affected_field,
            "affected_value": affected_value,
        })
    return findings, exported


def _classify(
    comp: CompositeRegion, field_hit: FieldValue | None, page_text: str,
    page_size: tuple[int, int] | None,
) -> tuple[str, str]:
    sources = set(comp.sources)
    if field_hit:
        if field_hit.group in PARTY_GROUPS and field_hit.value_type == "string":
            return "replaced_name", "Potentially replaced name"
        mapped = FIELD_TAMPER_TYPES.get(field_hit.value_type)
        if mapped:
            return mapped
    if "copy_move" in sources:
        return "copy_paste_region", "Duplicated (copy/paste) region"
    if "pdf_annotation" in sources:
        return "overlay_annotation", "Value overlaid by an annotation"
    if "embedded_image_mismatch" in sources:
        return "image_replacement", "Possible replaced image object"
    if "pdf_font_mix" in sources:
        return "added_text", "Potentially added or re-set text"
    if sources & {"txt_stroke_weight_anomaly", "txt_glyph_size_anomaly"}:
        return "font_substitution", "Inconsistent font characteristics"
    if SIGNATURE_TERMS.search(page_text) and page_size and comp.box["y"] > page_size[1] * 0.6:
        return "signature_or_stamp", "Signature / stamp area anomaly"
    return "region_anomaly", "Unattributed region anomaly"
