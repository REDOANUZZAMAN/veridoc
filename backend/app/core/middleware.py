"""Security headers, request correlation ids and a global rate limit."""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.errors import RateLimited
from app.core.logging import get_logger

logger = get_logger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        request.state.client_ip = _client_ip(request)
        started = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["x-request-id"] = rid
        duration = (time.perf_counter() - started) * 1000
        response.headers["x-response-time-ms"] = f"{duration:.1f}"
        if not request.url.path.endswith(("/health", "/ready")):
            logger.info(
                "request",
                extra={
                    "rid": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round(duration, 1),
                },
            )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        h.setdefault("Cross-Origin-Resource-Policy", "same-site")
        h.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
        )
        # Document bytes and reports must never be cached by intermediaries.
        if "/file" in request.url.path or "/render" in request.url.path or "/export" in request.url.path:
            h["Cache-Control"] = "private, no-store, max-age=0"
        if settings.is_production:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        h.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; img-src 'self' data:",
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Coarse per-IP limit. Endpoint-specific limits are applied in the routes."""

    async def dispatch(self, request: Request, call_next):
        from app.core.ratelimit import limiter

        if request.url.path.startswith(settings.api_prefix):
            try:
                limiter.check(f"global:{_client_ip(request)}", settings.rate_limit_default)
            except RateLimited as exc:
                return JSONResponse(status_code=exc.status_code, content=exc.payload())
        return await call_next(request)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
