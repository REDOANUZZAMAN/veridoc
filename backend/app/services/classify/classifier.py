"""Explainable document classifier.

Deliberately not a black box: the score is a weighted sum of term hits plus a
few structural bonuses, and every contribution is returned as evidence. The
confidence is the normalised margin between the best and the runner-up type, so
an ambiguous page yields a low confidence instead of a confident guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.db.enums import DOCUMENT_TYPE_LABELS, DocumentType
from app.services.classify.taxonomy import SIGNATURES, TypeSignature
from app.services.extract.normalize import find_money_tokens, normalize_text

CLASSIFIER_NAME = "lexical-structural-classifier"
CLASSIFIER_VERSION = "1.3.0"

WEIGHTS = {"strong": 3.0, "supporting": 1.5, "weak": 0.6, "negative": -2.0}
MIN_SCORE_FOR_TYPE = 2.6


@dataclass(slots=True)
class ClassificationResult:
    document_type: str
    label: str
    confidence: float
    scores: dict[str, float]
    matched_terms: dict[str, list[str]]
    alternatives: list[dict]
    method: str = CLASSIFIER_NAME
    version: str = CLASSIFIER_VERSION
    structural: dict = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "document_type": self.document_type,
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "scores": {k: round(v, 2) for k, v in sorted(
                self.scores.items(), key=lambda kv: -kv[1])},
            "matched_terms": self.matched_terms,
            "alternatives": self.alternatives,
            "classifier": self.method,
            "classifier_version": self.version,
            "structural": self.structural,
            "note": self.note,
        }


def _term_hits(text: str, terms: tuple[str, ...]) -> list[str]:
    hits = []
    for term in terms:
        pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, text, re.I):
            hits.append(term)
    return hits


def _structural_features(text: str, page_count: int, page_sizes: list[tuple[int, int]]) -> dict:
    money = find_money_tokens(text)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    item_like = sum(
        1 for ln in lines
        if re.search(r"[A-Za-z]{3,}.*?\d+[.,]\d{2}\s*$", ln.strip())
    )
    aspect = None
    if page_sizes:
        w, h = page_sizes[0]
        if h:
            ratio = w / h
            aspect = "card" if 1.3 <= ratio <= 1.9 else ("portrait" if ratio < 1 else "landscape")
    return {
        "page_count": page_count,
        "money_token_count": len(money),
        "line_item_like_rows": item_like,
        "line_count": len(lines),
        "has_totals_block": bool(re.search(r"\b(sub\s*total|grand\s*total|total\s*due|amount\s*due)\b", text, re.I)),
        "first_page_aspect": aspect,
    }


def classify(
    text: str, *, page_count: int = 1, page_sizes: list[tuple[int, int]] | None = None
) -> ClassificationResult:
    clean = normalize_text(text or "")
    # Keep line structure for the structural pass, normalised text for terms.
    structural = _structural_features(text or "", page_count, page_sizes or [])

    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    for doc_type, sig in SIGNATURES.items():
        score = 0.0
        hits: list[str] = []
        for bucket in ("strong", "supporting", "weak", "negative"):
            terms = getattr(sig, bucket)
            found = _term_hits(clean, terms)
            score += WEIGHTS[bucket] * len(found)
            if bucket != "negative":
                hits.extend(found)
            else:
                hits.extend(f"-{t}" for t in found)
        score += _structural_bonus(sig, structural)
        if score > 0:
            scores[doc_type] = score
            matched[doc_type] = hits

    if not scores:
        return ClassificationResult(
            document_type=DocumentType.OTHER, label=DOCUMENT_TYPE_LABELS[DocumentType.OTHER],
            confidence=0.25, scores={}, matched_terms={}, alternatives=[],
            structural=structural,
            note="No document-type signature matched; extraction used the generic schema.",
        )

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_type, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if top_score < MIN_SCORE_FOR_TYPE:
        return ClassificationResult(
            document_type=DocumentType.OTHER, label=DOCUMENT_TYPE_LABELS[DocumentType.OTHER],
            confidence=round(min(0.4, 0.15 + top_score / 20), 4), scores=scores,
            matched_terms=matched,
            alternatives=[{"document_type": t, "label": DOCUMENT_TYPE_LABELS[t],
                           "confidence": round(s / max(top_score * 2, 1), 4)} for t, s in ranked[:3]],
            structural=structural,
            note=("Evidence was too weak to assign a specific document type "
                  f"(best score {top_score:.1f} < threshold {MIN_SCORE_FOR_TYPE})."),
        )

    # Margin-based confidence: dominance over the runner-up, damped by absolute evidence.
    margin = (top_score - second_score) / max(top_score, 1.0)
    evidence = min(top_score / 14.0, 1.0)
    confidence = 0.45 + 0.35 * margin + 0.20 * evidence
    confidence = max(0.40, min(0.985, confidence))

    alternatives = [
        {"document_type": t, "label": DOCUMENT_TYPE_LABELS[t],
         "confidence": round(max(0.02, (s / top_score) * confidence * 0.8), 4)}
        for t, s in ranked[1:4]
    ]
    return ClassificationResult(
        document_type=top_type, label=DOCUMENT_TYPE_LABELS[top_type], confidence=confidence,
        scores=scores, matched_terms={top_type: matched[top_type], **{
            t: matched[t][:6] for t, _ in ranked[1:3]}},
        alternatives=alternatives, structural=structural,
        note=f"Matched {len(matched[top_type])} signature terms for {DOCUMENT_TYPE_LABELS[top_type]}.",
    )


def _structural_bonus(sig: TypeSignature, features: dict) -> float:
    bonus = 0.0
    if sig.expects_line_items and features["line_item_like_rows"] >= 3:
        bonus += 1.2
    if sig.expects_totals and features["has_totals_block"]:
        bonus += 1.0
    if not sig.expects_totals and features["has_totals_block"]:
        bonus -= 0.8
    lo, hi = sig.typical_pages
    if not (lo <= features["page_count"] <= hi):
        bonus -= 0.6
    if sig.aspect_hint and features.get("first_page_aspect") == sig.aspect_hint:
        bonus += 1.0
    return bonus
