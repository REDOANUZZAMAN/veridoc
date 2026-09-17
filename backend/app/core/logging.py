"""PII-aware logging.

Documents handled by this platform contain medical and identity data. The
formatter therefore (a) never receives document bodies - callers pass ids and
counts only - and (b) redacts anything that still looks like PII.
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Any

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_DIGITS = re.compile(r"\b\d{6,}\b")
_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_SENSITIVE_KEYS = {
    "password", "token", "authorization", "secret", "api_key", "raw_text",
    "patient_name", "customer_name", "dob", "national_id", "address", "diagnosis",
}

_configured = False


def redact(value: Any) -> Any:
    """Recursively strip values that must never reach a log sink."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).lower() in _SENSITIVE_KEYS:
                out[k] = "[redacted]"
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        v = _EMAIL.sub("[email]", value)
        v = _CARD.sub("[card]", v)
        v = _LONG_DIGITS.sub("[number]", v)
        return v[:500]
    return value


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.msg = redact(record.msg)
        base = super().format(record)
        extras = {
            k: redact(v)
            for k, v in record.__dict__.items()
            if k
            not in logging.LogRecord("", 0, "", 0, "", (), None).__dict__
            and k not in {"message", "asctime", "taskName"}
        }
        if extras:
            base += " | " + " ".join(f"{k}={v}" for k, v in extras.items())
        return base


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("botocore", "boto3", "urllib3", "pdfminer", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
