"""Append-only audit trail with a tamper-evident hash chain.

Each entry hashes its own canonical content together with the previous entry's
hash. Rewriting or removing any historic row invalidates every hash after it,
which ``verify_chain`` demonstrates on demand.

PII discipline: this service stores *references and diffs of structured fields*,
never document text. ``_sanitise`` truncates and drops keys that could carry a
medical or identity payload.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.audit import AuditLog

logger = get_logger(__name__)

GENESIS = "0" * 64
MAX_VALUE_CHARS = 400
# Redacted before an entry is written. Two groups, for two reasons:
#
#   secrets        - must never exist outside the environment.
#   special-category / identity data - the audit log is append-only and retained
#       for years, so duplicating health or identity details into it would widen
#       the exposure of the most sensitive fields for no accountability benefit.
#       The claim's own record already holds them, under normal access control
#       and retention. Ordinary identifiers that the audit trail *needs* to be
#       useful (claim numbers, document references, the acting user) are kept.
FORBIDDEN_KEYS = {
    # secrets
    "password", "password_hash", "token", "access_token", "refresh_token", "secret",
    "api_key", "authorization", "jwt", "credential",
    # document bodies
    "raw_text", "text", "words", "ocr_words", "file_bytes", "content",
    # special-category and identity data
    "patient_name", "date_of_birth", "dob", "customer_dob", "national_id", "passport_number",
    "address", "diagnosis", "procedure", "medications", "account_number", "iban",
    "gender", "sex",
}


def _sanitise(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if str(k).lower() in FORBIDDEN_KEYS else _sanitise(v, depth + 1))
            for k, v in list(value.items())[:40]
        }
    if isinstance(value, (list, tuple)):
        return [_sanitise(v, depth + 1) for v in value[:20]]
    if isinstance(value, str):
        return value[:MAX_VALUE_CHARS]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_VALUE_CHARS]


def canonical_payload(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, entry: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_payload(entry)).encode("utf-8")).hexdigest()


def record(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor=None,
    summary: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    # Serialise chain appends so two concurrent writers cannot fork the chain.
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('veridoc_audit_chain'))"))
    except Exception:  # pragma: no cover - non-PostgreSQL backends
        pass

    prev = db.execute(
        select(AuditLog.entry_hash).order_by(AuditLog.seq.desc()).limit(1)
    ).scalar_one_or_none() or GENESIS

    entry = {
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "actor_id": getattr(actor, "id", None),
        "actor_email": getattr(actor, "email", None),
        "actor_role": getattr(actor, "role_name", None),
        "summary": (summary or "")[:400],
        "before": _sanitise(before) if before is not None else None,
        "after": _sanitise(after) if after is not None else None,
        "metadata": _sanitise(metadata or {}),
        "ip_address": ip_address,
        "request_id": request_id,
    }
    log = AuditLog(
        actor_id=entry["actor_id"],
        actor_email=entry["actor_email"],
        actor_role=entry["actor_role"],
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        summary=entry["summary"] or None,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:320] or None,
        request_id=request_id,
        before_state=entry["before"],
        after_state=entry["after"],
        metadata_json=entry["metadata"],
        prev_hash=prev,
        entry_hash=compute_hash(prev, entry),
    )
    db.add(log)
    db.flush()
    return log


def rebuild_entry(log: AuditLog) -> dict:
    return {
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "actor_id": log.actor_id,
        "actor_email": log.actor_email,
        "actor_role": log.actor_role,
        "summary": log.summary or "",
        "before": log.before_state,
        "after": log.after_state,
        "metadata": log.metadata_json or {},
        "ip_address": log.ip_address,
        "request_id": log.request_id,
    }


def verify_chain(db: Session, *, limit: int | None = None) -> dict:
    """Recompute the chain and report the first divergence, if any."""
    query = select(AuditLog).order_by(AuditLog.seq.asc())
    if limit:
        query = query.limit(limit)
    rows = list(db.execute(query).scalars())
    prev = GENESIS
    broken_at = None
    for row in rows:
        expected = compute_hash(prev, rebuild_entry(row))
        if row.prev_hash != prev or row.entry_hash != expected:
            broken_at = {
                "seq": row.seq, "id": row.id, "action": row.action,
                "stored_entry_hash": row.entry_hash, "recomputed_entry_hash": expected,
                "stored_prev_hash": row.prev_hash, "expected_prev_hash": prev,
            }
            break
        prev = row.entry_hash
    total = db.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    return {
        "entries_checked": len(rows),
        "entries_total": int(total),
        "intact": broken_at is None,
        "head_hash": prev,
        "broken_at": broken_at,
        "algorithm": "sha256(prev_hash || canonical_json(entry))",
    }
