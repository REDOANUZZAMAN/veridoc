"""Typography and layout forensics.

Text that was replaced in an existing document rarely matches the original
typesetting exactly. This module measures four independent properties per line
and flags words that break the local pattern:

* baseline alignment    - vertical offset of a word against its line's baseline
* glyph size            - word height against the line's median height
* stroke weight         - mean stroke thickness from a distance transform
* recognition agreement - a low-confidence island inside a high-confidence line

For digital PDFs it additionally reads the *actual* font name and size of every
character, so a number set in a different font than its own line is detectable
exactly rather than statistically.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np

from app.core.logging import get_logger
from app.db.enums import FindingCategory, Severity
from app.services.forensics.base import (
    RawFinding,
    clamp,
    region,
    severity_from_confidence,
)
from app.services.ocr.base import OcrPageResult, OcrWord

logger = get_logger(__name__)

DETECTOR = "typography-layout-forensics"
DETECTOR_VERSION = "1.4.0"

_NUMERIC = re.compile(r"[\d]")
_MONEYISH = re.compile(r"^[\$€£₹৳]?[\d][\d,.]*$")
MIN_WORDS_PER_LINE = 3


@dataclass(slots=True)
class LayoutReport:
    findings: list[RawFinding] = field(default_factory=list)
    suspect_regions: list[dict] = field(default_factory=list)
    features: dict = field(default_factory=dict)


def _word_region(words: list[OcrWord], pad: int = 3) -> dict:
    x0 = min(w.bbox.x for w in words) - pad
    y0 = min(w.bbox.y for w in words) - pad
    x1 = max(w.bbox.x + w.bbox.width for w in words) + pad
    y1 = max(w.bbox.y + w.bbox.height for w in words) + pad
    return region(max(x0, 0), max(y0, 0), x1 - max(x0, 0), y1 - max(y0, 0))


def analyze_layout(page: OcrPageResult, page_png: bytes | None) -> LayoutReport:
    report = LayoutReport()
    lines = [ln for ln in page.lines() if len(ln) >= MIN_WORDS_PER_LINE]
    if not lines:
        report.features = {"lines_analysed": 0, "note": "Too few words per line for layout analysis."}
        return report

    gray = _load_gray(page_png)
    baseline_hits: list[dict] = []
    size_hits: list[dict] = []
    stroke_hits: list[dict] = []
    conf_hits: list[dict] = []

    for line in lines:
        ordered = sorted(line, key=lambda w: w.bbox.x)
        heights = np.array([w.bbox.height for w in ordered], dtype=float)
        bottoms = np.array([w.bbox.y + w.bbox.height for w in ordered], dtype=float)
        med_h = float(np.median(heights)) or 1.0
        med_bottom = float(np.median(bottoms))
        bottom_dev = np.abs(bottoms - med_bottom) / med_h

        for w, dev in zip(ordered, bottom_dev, strict=True):
            if dev > 0.34 and len(ordered) >= 5:
                baseline_hits.append({
                    "word": w, "deviation": float(dev), "line_median_height": med_h,
                })
        ratios = heights / med_h
        for w, ratio in zip(ordered, ratios, strict=True):
            if (ratio > 1.42 or ratio < 0.66) and w.bbox.height > 6:
                size_hits.append({"word": w, "height_ratio": float(ratio),
                                  "size_deviation": float(abs(ratio - 1.0)),
                                  "line_median_height": med_h})

        confs = np.array([w.confidence for w in ordered], dtype=float)
        line_conf = float(np.median(confs))
        if line_conf > 0.82:
            for w, c in zip(ordered, confs, strict=True):
                if c < 0.58:
                    conf_hits.append({"word": w, "word_confidence": float(c),
                                      "line_confidence": line_conf})

        if gray is not None:
            widths = []
            for w in ordered:
                sw = _stroke_width(gray, w)
                widths.append(sw)
            valid = [(w, s) for w, s in zip(ordered, widths, strict=True) if s is not None]
            if len(valid) >= 5:
                arr = np.array([s for _, s in valid], dtype=float)
                med = float(np.median(arr)) or 1e-6
                for (w, s) in valid:
                    rel = abs(s - med) / med
                    if rel > 0.42:
                        stroke_hits.append({"word": w, "stroke_width": round(s, 3),
                                            "line_median_stroke": round(med, 3),
                                            "relative_deviation": round(rel, 3)})

    report.features = {
        "lines_analysed": len(lines),
        "baseline_outliers": len(baseline_hits),
        "glyph_size_outliers": len(size_hits),
        "stroke_outliers": len(stroke_hits),
        "low_confidence_islands": len(conf_hits),
        "stroke_analysis_available": gray is not None,
    }

    report.findings.extend(_emit(
        baseline_hits, page.page_number,
        code="TXT_BASELINE_ANOMALY",
        title="Text baseline misalignment",
        body=("One or more words sit off the baseline shared by the rest of their line. Text "
              "inserted over an existing document is frequently a fraction of a line-height out "
              "of register; uneven scanning can also cause it."),
        metric_key="deviation", base=0.5, span=0.55, ceiling=Severity.MEDIUM,
        report=report,
    ))
    report.findings.extend(_emit(
        size_hits, page.page_number,
        code="TXT_GLYPH_SIZE_ANOMALY",
        title="Glyph size inconsistent within a line",
        body=("A word's height departs sharply from the median height of its own line, which is "
              "what happens when replacement text is set at a slightly different point size."),
        metric_key="size_deviation", base=0.46, span=0.26, ceiling=Severity.MEDIUM,
        report=report,
    ))
    report.findings.extend(_emit(
        stroke_hits, page.page_number,
        code="TXT_STROKE_WEIGHT_ANOMALY",
        title="Stroke weight inconsistent within a line",
        body=("Mean stroke thickness for this word differs materially from its neighbours, "
              "indicating a different typeface, weight or rendering path for that word."),
        metric_key="relative_deviation", base=0.52, span=0.5, ceiling=Severity.HIGH,
        report=report,
    ))
    report.findings.extend(_emit(
        conf_hits, page.page_number,
        code="TXT_LOW_CONFIDENCE_ISLAND",
        title="Isolated low-confidence text inside clean text",
        body=("The OCR engine was markedly less certain about this word than about the rest of "
              "its line. Retouched or re-rendered characters commonly read this way - so do "
              "smudges and stamps overlapping text."),
        metric_key="word_confidence", base=0.42, span=0.0, ceiling=Severity.MEDIUM, report=report,
    ))
    return report


def _emit(
    hits: list[dict], page_number: int, *, code: str, title: str, body: str, metric_key: str,
    base: float, span: float, ceiling: str, report: LayoutReport, limit: int = 4,
) -> list[RawFinding]:
    if not hits:
        return []
    # Numeric content is what matters on a financial document, so rank it first.
    hits.sort(key=lambda h: (not _NUMERIC.search(h["word"].text), -abs(h.get(metric_key, 0))))
    out: list[RawFinding] = []
    for hit in hits[:limit]:
        word: OcrWord = hit["word"]
        metric = float(hit.get(metric_key, 0.0))
        numeric = bool(_NUMERIC.search(word.text))
        confidence = clamp(base + (span * min(metric, 1.6)) + (0.06 if numeric else 0.0), 0.3, 0.9)
        reg = _word_region([word])
        report.suspect_regions.append({
            "source": code.lower(), "region": reg, "page": page_number,
            "confidence": confidence, "text": word.text,
        })
        out.append(RawFinding(
            code=code, category=FindingCategory.FORENSICS,
            severity=severity_from_confidence(confidence, ceiling),
            title=f"{title}: “{word.text[:40]}” (page {page_number})",
            description=body + (
                " The affected token contains digits, so if this document drives a payment the "
                "value itself should be confirmed against the issuer's records."
                if numeric else ""
            ),
            confidence=confidence, detector=DETECTOR, model_version=DETECTOR_VERSION,
            page=page_number, region=reg,
            evidence={"token": word.text[:60], "metric": metric_key,
                      "value": round(metric, 4),
                      **{k: (round(v, 4) if isinstance(v, float) else v)
                         for k, v in hit.items() if k != "word"},
                      "ocr_confidence": round(word.confidence, 4)},
            recommendation="Click the finding to inspect the highlighted token in the viewer.",
            extras={"signal_group": "text"},
        ))
    return out


def _load_gray(page_png: bytes | None):
    if not page_png:
        return None
    try:
        import cv2

        arr = np.frombuffer(page_png, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None


def _stroke_width(gray, word: OcrWord) -> float | None:
    """Mean stroke half-width via a distance transform of the binarised crop."""
    import cv2

    b = word.bbox
    h, w = gray.shape[:2]
    x0, y0 = max(b.x, 0), max(b.y, 0)
    x1, y1 = min(b.x + b.width, w), min(b.y + b.height, h)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    crop = gray[y0:y1, x0:x1]
    try:
        _, binary = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink = float((binary > 0).mean())
        if ink < 0.02 or ink > 0.9:
            return None
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
        ridge = dist[dist > 0.6]
        if ridge.size < 8:
            return None
        return float(np.mean(ridge) * 2.0) / max(float(b.height), 1.0)
    except Exception:
        return None


def analyze_pdf_fonts(pdf_bytes: bytes, page_sizes: dict[int, tuple[int, int]]) -> LayoutReport:
    """Exact per-character font inspection for digital PDFs."""
    report = LayoutReport()
    try:
        import pdfplumber
    except Exception as exc:
        report.features = {"error": f"pdfplumber unavailable: {exc}"}
        return report

    mixed_lines = 0
    inspected_lines = 0
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                render_w, render_h = page_sizes.get(page_index, (int(page.width), int(page.height)))
                sx = render_w / float(page.width or 1)
                sy = render_h / float(page.height or 1)
                # Cluster characters into text lines by baseline, with a tolerance
                # proportional to glyph size. A fixed bucket splits a line whenever
                # two fonts with different ascents sit side by side - which is
                # precisely the case this detector exists to find.
                candidates = [c for c in page.chars if c.get("text", "").strip()]
                rows: list[tuple[float, list[dict]]] = []
                for ch in sorted(candidates, key=lambda c: (float(c["bottom"]),
                                                            float(c["x0"]))):
                    baseline = float(ch["bottom"])
                    tolerance = max(2.5, float(ch.get("size", 10)) * 0.55)
                    for i, (ref, bucket) in enumerate(rows):
                        if abs(ref - baseline) <= tolerance:
                            bucket.append(ch)
                            rows[i] = (ref, bucket)
                            break
                    else:
                        rows.append((baseline, [ch]))
                for _, chars in rows:
                    if len(chars) < 8:
                        continue
                    inspected_lines += 1
                    fonts = [c.get("fontname", "?") for c in chars]
                    dominant = max(set(fonts), key=fonts.count)
                    share = fonts.count(dominant) / len(fonts)
                    if share >= 0.995:
                        continue
                    outliers = [c for c in chars if c.get("fontname") != dominant]
                    # Group the outlying characters into contiguous tokens.
                    outliers.sort(key=lambda c: float(c["x0"]))
                    token = "".join(c["text"] for c in outliers)[:40]
                    if len(outliers) > len(chars) * 0.55:
                        continue  # genuinely mixed styling (headings, bold labels)
                    mixed_lines += 1
                    numeric = bool(_NUMERIC.search(token))
                    confidence = clamp(0.62 + (0.16 if numeric else 0.0) +
                                       min(len(outliers) / 40.0, 0.12), 0.5, 0.92)
                    x0 = min(float(c["x0"]) for c in outliers) * sx
                    x1 = max(float(c["x1"]) for c in outliers) * sx
                    y0 = min(float(c["top"]) for c in outliers) * sy
                    y1 = max(float(c["bottom"]) for c in outliers) * sy
                    reg = region(int(x0) - 2, int(y0) - 2, int(x1 - x0) + 4, int(y1 - y0) + 4)
                    report.suspect_regions.append({
                        "source": "pdf_font_mix", "region": reg, "page": page_index,
                        "confidence": confidence, "text": token,
                    })
                    report.findings.append(RawFinding(
                        code="PDF_TEXT_FONT_MIX_IN_LINE", category=FindingCategory.FORENSICS,
                        severity=severity_from_confidence(confidence),
                        title=f"Font change inside a text line: “{token}” (page {page_index})",
                        description=(
                            f"Characters on this line are set in {sorted(set(fonts))} while the "
                            f"line is dominated by {dominant}. In a PDF this is an exact "
                            "measurement, not an estimate: the highlighted characters were drawn "
                            "with a different font resource from the rest of their line, which is "
                            "the usual footprint of text edited into an existing document. "
                            "Templates that bold a single value legitimately do this too."
                        ),
                        confidence=confidence, detector=DETECTOR, model_version=DETECTOR_VERSION,
                        page=page_index, region=reg,
                        evidence={"token": token, "dominant_font": dominant,
                                  "fonts_in_line": sorted(set(fonts)),
                                  "outlier_char_count": len(outliers),
                                  "line_char_count": len(chars),
                                  "dominant_share": round(share, 4),
                                  "sizes": sorted({round(float(c.get('size', 0)), 1)
                                                   for c in chars})},
                        recommendation="Confirm the highlighted value directly with the issuer.",
                        extras={"signal_group": "text"},
                    ))
    except Exception as exc:
        logger.warning("pdf_font_analysis_failed", extra={"detail": str(exc)[:160]})
        report.features = {"error": type(exc).__name__}
        return report

    report.features = {
        "lines_inspected": inspected_lines,
        "lines_with_font_mix": mixed_lines,
        "method": "pdfplumber_char_fontnames",
    }
    return report
