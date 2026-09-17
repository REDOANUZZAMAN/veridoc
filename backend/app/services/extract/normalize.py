"""Value normalisation shared by extraction, the consistency engine and cross-document matching."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "৳": "BDT", "S$": "SGD"}
_MONEY_RE = re.compile(r"[-+]?\(?\s*(?:[\$€£₹৳]|USD|EUR|GBP|SGD|AUD|INR|BDT)?\s*[\d][\d,\. ]*\)?")
_NUM_CLEAN = re.compile(r"[^\d.,\-]")

DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%d %b, %Y",
    "%Y%m%d", "%d/%m/%y", "%m/%d/%y",
]


def collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_text(value: str) -> str:
    v = unicodedata.normalize("NFKD", value or "")
    v = "".join(c for c in v if not unicodedata.combining(c))
    return collapse_ws(v)


def normalize_name(value: str) -> str:
    """Casefold, drop honorifics and punctuation so two spellings compare cleanly."""
    v = normalize_text(value).lower()
    v = re.sub(r"\b(mr|mrs|ms|miss|dr|prof|md|sr|jr)\b\.?", " ", v)
    v = re.sub(r"[^a-z0-9 ]", " ", v)
    return collapse_ws(v)


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize_text(value).upper())


def parse_money(value: str | None) -> tuple[Decimal | None, str | None]:
    """Returns (amount, currency_code|None). Handles 1,234.56 / 1.234,56 / (250.00)."""
    if value is None:
        return None, None
    raw = normalize_text(str(value))
    if not raw:
        return None, None
    currency = None
    for sym, code in CURRENCY_SYMBOLS.items():
        if sym in raw:
            currency = code
            break
    m = re.search(r"\b(USD|EUR|GBP|SGD|AUD|INR|BDT)\b", raw, re.I)
    if m:
        currency = m.group(1).upper()
    negative = raw.strip().startswith("(") and raw.strip().endswith(")") or raw.strip().startswith("-")
    cleaned = _NUM_CLEAN.sub("", raw)
    if not cleaned:
        return None, currency
    # Decide which separator is the decimal mark.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        cleaned = cleaned.replace(",", ".") if len(parts[-1]) == 2 else cleaned.replace(",", "")
    cleaned = cleaned.replace("-", "").strip(".")
    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None, currency
    return (-amount if negative else amount), currency


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = normalize_text(str(value))
    raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw, flags=re.I)
    m = re.search(
        r"\b(\d{1,4}[-/.\s][A-Za-z0-9]{1,9}[-/.\s]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b", raw
    )
    candidate = m.group(1) if m else raw
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(candidate.replace(",", "").strip(), fmt).date()
        except ValueError:
            continue
    try:
        from dateutil import parser as dateparser

        return dateparser.parse(candidate, dayfirst=False, fuzzy=True).date()
    except Exception:
        return None


def parse_number(value: str | None) -> Decimal | None:
    amount, _ = parse_money(value)
    return amount


def parse_percent(value: str | None) -> Decimal | None:
    if not value:
        return None
    m = re.search(r"([\d.]+)\s*%", str(value))
    if m:
        try:
            return Decimal(m.group(1))
        except InvalidOperation:
            return None
    return parse_number(value)


def normalize_value(value: str | None, value_type: str) -> str | None:
    if value is None:
        return None
    if value_type == "money":
        amount, _ = parse_money(value)
        return f"{amount:.2f}" if amount is not None else None
    if value_type == "date":
        d = parse_date(value)
        return d.isoformat() if d else None
    if value_type == "identifier":
        return normalize_identifier(value) or None
    if value_type in {"number", "percent"}:
        n = parse_number(value) if value_type == "number" else parse_percent(value)
        return str(n) if n is not None else None
    return collapse_ws(value) or None


def find_money_tokens(text: str) -> list[str]:
    return [t.strip() for t in _MONEY_RE.findall(text or "") if any(c.isdigit() for c in t)]


def person_similarity(a: str | None, b: str | None) -> float:
    """Strict same-person comparison.

    ``token_set_ratio`` - the right tool for asking whether two spellings of a
    name *disagree* - scores "Daniel Okonkwo" against "Amelia R. Okonkwo" highly,
    because the shared surname forms a complete subset. That is useless for the
    opposite question, "are these the same person?", which family policies make
    load-bearing: a dependant shares a surname with the policyholder but is not
    them. Order-sensitive token comparison keeps the two questions apart.
    """
    if not a or not b:
        return 0.0
    from rapidfuzz import fuzz

    return fuzz.token_sort_ratio(normalize_name(a), normalize_name(b)) / 100.0


def is_same_person(a: str | None, b: str | None, threshold: float = 0.80) -> bool:
    return person_similarity(a, b) >= threshold
