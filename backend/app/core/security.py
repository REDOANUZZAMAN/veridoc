"""Password hashing, JWT issuing/verification and HMAC-signed object URLs."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import AuthenticationError

_pwd = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _pwd.verify(raw, hashed)
    except Exception:
        return False


def password_strength_errors(raw: str) -> list[str]:
    errs = []
    if len(raw) < 10:
        errs.append("Password must be at least 10 characters.")
    if not any(c.isupper() for c in raw):
        errs.append("Password must contain an uppercase letter.")
    if not any(c.isdigit() for c in raw):
        errs.append("Password must contain a digit.")
    if not any(not c.isalnum() for c in raw):
        errs.append("Password must contain a symbol.")
    return errs


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(
    subject: str, role: str, token_type: TokenType = "access", *, session_id: str | None = None
) -> tuple[str, datetime]:
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    expires = _now() + ttl
    payload = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "sid": session_id or uuid.uuid4().hex,
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
        "jti": uuid.uuid4().hex,
        "iss": "veridoc",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], issuer="veridoc"
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Session expired. Please sign in again.") from None
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid authentication token.") from None
    if expected_type and payload.get("type") != expected_type:
        raise AuthenticationError("Incorrect token type for this operation.")
    return payload


# --- signed object URLs -------------------------------------------------------
# Uploaded documents are never public. The API hands out a short-lived,
# HMAC-signed relative URL bound to (resource, purpose, user).


def sign_resource(resource: str, purpose: str, user_id: str, ttl: int | None = None) -> dict[str, Any]:
    exp = int(time.time()) + (ttl or settings.signed_url_ttl_seconds)
    nonce = secrets.token_urlsafe(8)
    msg = f"{resource}|{purpose}|{user_id}|{exp}|{nonce}".encode()
    sig = hmac.new(settings.jwt_secret.encode(), msg, hashlib.sha256).hexdigest()
    return {"exp": exp, "nonce": nonce, "sig": sig, "uid": user_id}


def verify_resource_signature(
    resource: str, purpose: str, user_id: str, exp: int, nonce: str, sig: str
) -> None:
    if exp < int(time.time()):
        raise AuthenticationError("This download link has expired. Request a new one.")
    msg = f"{resource}|{purpose}|{user_id}|{exp}|{nonce}".encode()
    expected = hmac.new(settings.jwt_secret.encode(), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise AuthenticationError("Invalid download signature.")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_stream(chunks) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    for chunk in chunks:
        h.update(chunk)
        total += len(chunk)
    return h.hexdigest(), total
