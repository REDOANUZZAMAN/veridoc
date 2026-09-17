"""Schema-driven field extraction.

Given per-page OCR output (words + boxes) and a :class:`DocumentSchema`, this
engine locates each declared field, normalises the value, scores a confidence
and records the bounding box so the investigation viewer can highlight exactly
where a value came from.

Nothing here is specific to one document: labels, types and requirements all
come from ``extract/schema.py``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.services.extract.normalize import (
    normalize_text,
    normalize_value,
    parse_date,
    parse_money,
)
from app.services.extract.schema import FIELD_LIBRARY, DocumentSchema, FieldSpec
from app.services.ocr.base import OcrPageResult, OcrWord

EXTRACTOR_NAME = "schema-field-extractor"
EXTRACTOR_VERSION = "1.4.0"

_SEPARATORS = re.compile(r"^[\s:\-–—#=.\u00b7]+")
_TOTAL_WORDS = re.compile(
    r"\b(sub\s*total|grand\s*total|total|amount\s*due|balance|tax|vat|gst|discount|payable)\b", re.I
)
_ITEM_ROW = re.compile(
    r"^(?P<desc>[A-Za-z][A-Za-z0-9 ,.\-/&()'+]{2,80}?)\s{1,}"
    r"(?P<nums>(?:[-+]?[\d][\d,.]*\s+){0,3}[-+]?[\d][\d,.]*)$"
)


@dataclass(slots=True)
class LineView:
    page: int
    index: int
    text: str
    words: list[OcrWord]
    spans: list[tuple[int, int]]          # char span per word in ``text``
    top: int
    height: int

    def bbox_for_span(self, start: int, end: int) -> dict | None:
        # spans and words are built together, one span per word
        hits = [w for (s, e), w in zip(self.spans, self.words, strict=True)
                if s < end and e > start]
        if not hits:
            return None
        x0 = min(w.bbox.x for w in hits)
        y0 = min(w.bbox.y for w in hits)
        x1 = max(w.bbox.x + w.bbox.width for w in hits)
        y1 = max(w.bbox.y + w.bbox.height for w in hits)
        return {"x": x0, "y": y0, "width": max(x1 - x0, 1), "height": max(y1 - y0, 1)}

    def median_word_height(self) -> float:
        if not self.words:
            return 0.0
        heights = sorted(w.bbox.height for w in self.words)
        return float(heights[len(heights) // 2])

    def column_gap_threshold(self) -> float:
        """Minimum whitespace that separates a label from a value in a column.

        Derived from glyph height rather than from the line's own word spacing:
        a two-word line ("Total amount  $2,150.00") has no usable spacing
        statistics of its own. A word space is roughly a quarter of an em and a
        column gap is at least one em, so ~0.9 x glyph height separates them
        cleanly at any resolution.
        """
        return max(10.0, self.median_word_height() * 0.9)

    def median_word_gap(self) -> float:
        gaps = []
        for prev, nxt in zip(self.words, self.words[1:], strict=False):
            gaps.append(max(0, nxt.bbox.x - (prev.bbox.x + prev.bbox.width)))
        if not gaps:
            return 0.0
        gaps.sort()
        return float(gaps[len(gaps) // 2])

    def gap_before(self, char_index: int) -> float | None:
        """Horizontal whitespace immediately before the character at ``char_index``.

        A labelled field in a document is separated from its value either by a
        colon or by a column gap. Matching on that - rather than on position in
        the line - is what stops "HOSPITAL BILL" in a title from being read as
        the label "Hospital" with the value "BILL".
        """
        target = None
        for i, (start, end) in enumerate(self.spans):
            if end > char_index or start >= char_index:
                target = i
                break
        if target is None or target == 0:
            return None
        value_word = self.words[target]
        label_word = self.words[target - 1]
        return float(value_word.bbox.x - (label_word.bbox.x + label_word.bbox.width))

    def confidence_for_span(self, start: int, end: int) -> float:
        hits = [w for (s, e), w in zip(self.spans, self.words, strict=True)
                if s < end and e > start]
        if not hits:
            return 0.5
        return sum(w.confidence for w in hits) / len(hits)


@dataclass(slots=True)
class FieldValue:
    key: str
    label: str
    value_type: str
    value_raw: str
    value_normalized: str | None
    confidence: float
    page: int | None
    bbox: dict | None
    source: str
    required: bool
    group: str
    line_index: int | None = None
    matched_label: str | None = None

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "type": self.value_type,
            "value_raw": self.value_raw, "value": self.value_normalized,
            "confidence": round(self.confidence, 4), "page": self.page, "bbox": self.bbox,
            "source": self.source, "required": self.required, "group": self.group,
            "matched_label": self.matched_label,
        }


@dataclass(slots=True)
class LineItem:
    index: int
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None
    page: int
    bbox: dict | None
    raw: str

    def as_dict(self) -> dict:
        return {
            "index": self.index, "description": self.description,
            "quantity": float(self.quantity) if self.quantity is not None else None,
            "unit_price": float(self.unit_price) if self.unit_price is not None else None,
            "amount": float(self.amount) if self.amount is not None else None,
            "page": self.page, "bbox": self.bbox, "raw": self.raw,
        }


@dataclass(slots=True)
class ExtractionResult:
    document_type: str
    fields: list[FieldValue]
    line_items: list[LineItem]
    missing_required: list[str]
    extractor: str = EXTRACTOR_NAME
    version: str = EXTRACTOR_VERSION
    stats: dict = field(default_factory=dict)

    def by_key(self) -> dict[str, FieldValue]:
        return {f.key: f for f in self.fields}

    def value(self, key: str) -> str | None:
        f = self.by_key().get(key)
        return f.value_normalized if f else None

    def as_dict(self) -> dict:
        return {
            "document_type": self.document_type,
            "extractor": self.extractor,
            "extractor_version": self.version,
            "fields": [f.as_dict() for f in self.fields],
            "line_items": [i.as_dict() for i in self.line_items],
            "missing_required": self.missing_required,
            "stats": self.stats,
        }


def build_line_views(pages: list[OcrPageResult]) -> list[LineView]:
    views: list[LineView] = []
    for page in pages:
        for idx, line_words in enumerate(page.lines()):
            ordered = sorted(line_words, key=lambda w: w.bbox.x)
            text_parts, spans, cursor = [], [], 0
            for w in ordered:
                if text_parts:
                    cursor += 1  # joining space
                spans.append((cursor, cursor + len(w.text)))
                cursor += len(w.text)
                text_parts.append(w.text)
            text = " ".join(text_parts)
            if not text.strip():
                continue
            views.append(
                LineView(
                    page=page.page_number, index=idx, text=text, words=ordered, spans=spans,
                    top=min(w.bbox.y for w in ordered),
                    height=max(w.bbox.height for w in ordered),
                )
            )
    return views


def _all_label_regex(schema: DocumentSchema) -> re.Pattern:
    """Used to cut a captured value short when the next field label follows on the same line."""
    labels: list[str] = []
    for spec in schema.fields:
        labels.extend(spec.labels)
    labels = sorted({label for label in labels if len(label) >= 2}, key=len, reverse=True)
    if not labels:
        return re.compile(r"(?!x)x")
    joined = "|".join(re.escape(label).replace(r"\ ", r"\s+") for label in labels)
    return re.compile(rf"\b({joined})\b\s*[:#]", re.I)


def extract_fields(
    pages: list[OcrPageResult], schema: DocumentSchema, *, currency_hint: str | None = None
) -> ExtractionResult:
    lines = build_line_views(pages)
    next_label_re = _all_label_regex(schema)
    full_text = "\n".join(line.text for line in lines)

    required_keys = set(schema.required_keys())
    results: list[FieldValue] = []
    for spec in schema.fields:
        best = _extract_one(spec, lines, next_label_re)
        if best is None:
            best = _extract_by_pattern(spec, lines)
        if best is not None:
            best.required = spec.key in required_keys
            results.append(best)

    _apply_letterhead_fallback(results, schema, lines)
    currency = _resolve_currency(results, full_text, currency_hint)
    if currency and not any(f.key == "currency" for f in results):
        results.append(
            FieldValue(
                key="currency", label="Currency", value_type="string", value_raw=currency,
                value_normalized=currency, confidence=0.7, page=1, bbox=None,
                source="inferred", required=False, group="amounts",
                matched_label="inferred from amount symbols",
            )
        )

    items = _extract_line_items(lines) if schema.line_items else []
    missing = [
        key for key in schema.required_keys()
        if not any(f.key == key and f.value_normalized for f in results)
    ]
    stats = {
        "lines_scanned": len(lines),
        "fields_declared": len(schema.fields),
        "fields_found": len(results),
        "line_items_found": len(items),
        "mean_field_confidence": round(
            sum(f.confidence for f in results) / len(results), 4) if results else 0.0,
        "currency": currency,
    }
    return ExtractionResult(
        document_type=schema.document_type, fields=results, line_items=items,
        missing_required=missing, stats=stats,
    )


def _extract_one(
    spec: FieldSpec, lines: list[LineView], next_label_re: re.Pattern
) -> FieldValue | None:
    candidates: list[FieldValue] = []
    label_patterns = spec.compiled_labels()

    for li, line in enumerate(lines):
        for lab_idx, pattern in enumerate(label_patterns):
            m = pattern.search(line.text)
            if not m:
                continue
            # A word is only a field label when a separator or a column gap
            # follows it. Without this, "MEDICAL INVOICE" in a title reads as
            # the label "Invoice" with the value "…", and "Unit price" in a
            # table header reads as the label "Unit".
            has_separator = bool(m.groupdict().get("sep"))
            # A stacked layout - common on identity cards and printed forms - has
            # the label alone on its line with the value underneath. The label
            # must occupy the *whole* line: otherwise "Meridian General Hospital"
            # in a letterhead reads as the label "Hospital" with the strapline
            # beneath it as its value.
            label_owns_line = (
                not line.text[m.end():].strip() and not line.text[: m.start()].strip()
            )
            if not has_separator and not label_owns_line:
                threshold = line.column_gap_threshold()
                gap_after = line.gap_before(m.end())
                if gap_after is None or gap_after < threshold:
                    continue
                # A label with no separator must also *begin* its column, either
                # by starting the line or by having a column gap in front of it.
                # Without this, the word "procedure" at the end of a table row
                # ("Surgeon fee - laparoscopic procedure   1   1,850.00") is read
                # as a label whose value is the rest of the row.
                if line.text[: m.start()].strip():
                    gap_before = line.gap_before(m.start() + 1)
                    if gap_before is None or gap_before < threshold:
                        continue

            remainder = line.text[m.end():]
            value, span_start = _trim_value(remainder, next_label_re, spec)
            source, target_line = "ocr", line
            if not _plausible(value, spec) and spec.allow_next_line and li + 1 < len(lines):
                nxt = lines[li + 1]
                if nxt.page == line.page and abs(nxt.top - line.top) < line.height * 3.2:
                    alt, alt_start = _trim_value(nxt.text, next_label_re, spec)
                    if _plausible(alt, spec):
                        value, span_start, target_line, source = alt, alt_start, nxt, "ocr_next_line"
            if not _plausible(value, spec):
                continue

            abs_start = (m.end() if source == "ocr" else 0) + span_start
            abs_end = abs_start + len(value)
            bbox = target_line.bbox_for_span(abs_start, abs_end)
            ocr_conf = target_line.confidence_for_span(abs_start, abs_end)
            label_quality = 1.0 - (0.04 * lab_idx)
            penalty = 0.92 if source == "ocr_next_line" else 1.0
            normalized = normalize_value(value, spec.value_type)
            type_bonus = 1.0 if normalized else 0.72
            confidence = max(0.05, min(0.99, ocr_conf * label_quality * penalty * type_bonus))
            candidates.append(
                FieldValue(
                    key=spec.key, label=spec.label, value_type=spec.value_type,
                    value_raw=value[: spec.max_chars], value_normalized=normalized,
                    confidence=confidence, page=target_line.page, bbox=bbox, source=source,
                    required=spec.required, group=spec.group, line_index=target_line.index,
                    matched_label=spec.labels[lab_idx] if lab_idx < len(spec.labels) else None,
                )
            )
    if not candidates:
        return None
    # Prefer a normalisable value, then the highest confidence, then the earliest page.
    candidates.sort(key=lambda c: (c.value_normalized is None, -c.confidence, c.page or 99))
    return candidates[0]


# A letterhead names *one* kind of organisation. Matching the marker family to
# the field prevents an insurer's letterhead from being read as the hospital.
ORGANISATION_MARKERS: dict[str, re.Pattern] = {
    "hospital_name": re.compile(
        r"\b(hospital|clinic|medical|medicentre|surgery|health|healthcare|infirmary|"
        r"polyclinic|diagnostic|laborator|pharmac|dental|nursing)\b", re.I),
    "garage_name": re.compile(
        r"\b(collision|garage|workshop|body\s*shop|bodyshop|motors|autobody|auto|"
        r"service\s*cent(re|er)|tyre|panel)\b", re.I),
    "bank_name": re.compile(r"\b(bank|banking|building\s*society|credit\s*union)\b", re.I),
    "insurer_name": re.compile(
        r"\b(insurance|insurer|mutual|assurance|underwrit|indemnity)\b", re.I),
    "issuing_authority": re.compile(
        r"\b(agency|authority|office|department|ministry|constabulary|police|dvla|"
        r"passport|licensing|registrar|government)\b", re.I),
}
ORGANISATION_KEYS = tuple(ORGANISATION_MARKERS)


def _apply_letterhead_fallback(
    results: list[FieldValue], schema: DocumentSchema, lines: list[LineView]
) -> None:
    """Real documents name the issuer in the letterhead, not in a labelled field.

    When the schema expects an organisation and no labelled value was found, the
    first line of page 1 is used if it reads like an organisation name. The value
    is recorded with ``source="letterhead"`` and a reduced confidence so the
    provenance of the guess stays visible.
    """
    present = {f.key for f in results}
    wanted = [k for k in schema.field_keys if k in ORGANISATION_KEYS and k not in present]
    if not wanted:
        return
    # Only the first text line of page 1: a strapline underneath ("Health
    # claims - part A") would otherwise be read as the provider name.
    header = [line for line in lines if line.page == 1][:1]
    required_keys = set(schema.required_keys())
    for key in wanted:
        marker = ORGANISATION_MARKERS[key]
        for line in header:
            text = normalize_text(line.text)
            words = [w for w in text.split() if len(w) > 1]
            if len(words) < 2 or len(text) > 70 or not marker.search(text):
                continue
            if sum(ch.isdigit() for ch in text) > 4:
                continue
            spec = FIELD_LIBRARY[key]
            results.append(FieldValue(
                key=key, label=spec.label, value_type=spec.value_type, value_raw=text,
                value_normalized=normalize_value(text, spec.value_type),
                confidence=min(0.82, line.confidence_for_span(0, len(line.text)) * 0.85),
                page=1, bbox=line.bbox_for_span(0, len(line.text)), source="letterhead",
                required=key in required_keys, group=spec.group, line_index=line.index,
                matched_label="document letterhead",
            ))
            break


def _extract_by_pattern(spec: FieldSpec, lines: list[LineView]) -> FieldValue | None:
    if not spec.patterns:
        return None
    for line in lines:
        for pat in spec.patterns:
            m = re.search(pat, line.text, re.I)
            if not m:
                continue
            value = m.group(0).strip()
            normalized = normalize_value(value, spec.value_type)
            if not normalized:
                continue
            return FieldValue(
                key=spec.key, label=spec.label, value_type=spec.value_type, value_raw=value,
                value_normalized=normalized,
                confidence=min(0.9, line.confidence_for_span(m.start(), m.end()) * 0.85),
                page=line.page, bbox=line.bbox_for_span(m.start(), m.end()),
                source="pattern", required=spec.required, group=spec.group,
                line_index=line.index, matched_label=f"pattern:{pat}",
            )
    return None


def _trim_value(remainder: str, next_label_re: re.Pattern, spec: FieldSpec) -> tuple[str, int]:
    sep = _SEPARATORS.match(remainder)
    offset = sep.end() if sep else 0
    body = remainder[offset:]
    cut = next_label_re.search(body)
    if cut and cut.start() > 0:
        body = body[: cut.start()]
    body = body.strip(" |\t")
    if spec.value_type in {"money", "number", "percent"}:
        m = re.search(r"[-+(]?\s*(?:[\$€£₹৳]|USD|EUR|GBP|SGD|AUD|INR|BDT)?\s*[\d][\d,.\s]*\)?%?", body)
        if m:
            inner = m.group(0).strip()
            offset += body.find(inner)
            return inner, offset
    if spec.value_type == "date":
        m = re.search(
            r"(\d{1,4}[-/.\s][A-Za-z0-9]{1,9}[-/.\s]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})", body
        )
        if m:
            offset += m.start()
            return m.group(1).strip(), offset
    words = body.split()
    if spec.value_type == "identifier" and words:
        # Reference numbers contain digits. Preferring the first token that does
        # keeps a neighbouring caption ("PHOTOGRAPH  PN-4471829") from being read
        # as the value when OCR merges two columns onto one line.
        for word in words:
            token = word.strip(".,;")
            if any(ch.isdigit() for ch in token) and len(token) >= 3:
                return token, offset + body.find(word)
        return words[0].strip(".,;"), offset
    return normalize_text(body)[: spec.max_chars], offset


def _plausible(value: str, spec: FieldSpec) -> bool:
    if not value or len(value) < 1:
        return False
    if spec.value_type == "money":
        amount, _ = parse_money(value)
        return amount is not None
    if spec.value_type == "date":
        return parse_date(value) is not None
    if spec.value_type == "identifier":
        return bool(re.search(r"[A-Za-z0-9]{3,}", value))
    if spec.value_type in {"number", "percent"}:
        return bool(re.search(r"\d", value))
    return len(value.strip()) >= 2 and bool(re.search(r"[A-Za-z0-9]", value))


def _resolve_currency(fields: list[FieldValue], text: str, hint: str | None) -> str | None:
    for f in fields:
        if f.key == "currency" and f.value_normalized:
            return f.value_normalized.upper()[:3]
    m = re.search(r"\b(USD|EUR|GBP|SGD|AUD|INR|BDT)\b", text)
    if m:
        return m.group(1).upper()
    for sym, code in (("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("₹", "INR"), ("৳", "BDT")):
        if sym in text:
            return code
    return hint


def _extract_line_items(lines: list[LineView]) -> list[LineItem]:
    items: list[LineItem] = []
    for line in lines:
        text = line.text.strip()
        if len(text) < 6 or _TOTAL_WORDS.search(text):
            continue
        m = _ITEM_ROW.match(text)
        if not m:
            continue
        desc = normalize_text(m.group("desc"))
        nums = [n for n in re.split(r"\s+", m.group("nums").strip()) if n]
        parsed = [parse_money(n)[0] for n in nums]
        parsed = [p for p in parsed if p is not None]
        if not parsed or len(desc) < 3:
            continue
        quantity = unit_price = None
        amount = parsed[-1]
        if len(parsed) >= 3:
            quantity, unit_price = parsed[0], parsed[1]
        elif len(parsed) == 2:
            if parsed[0] == parsed[0].to_integral_value() and parsed[0] < 1000:
                quantity = parsed[0]
            else:
                unit_price = parsed[0]
        if amount is None or amount == 0:
            continue
        items.append(
            LineItem(
                index=len(items) + 1, description=desc[:120], quantity=quantity,
                unit_price=unit_price, amount=amount, page=line.page,
                bbox=line.bbox_for_span(0, len(text)), raw=text[:200],
            )
        )
    return items
