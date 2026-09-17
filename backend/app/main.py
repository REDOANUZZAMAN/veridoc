"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import PIPELINE_VERSION, RULES_VERSION, settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)

logger = get_logger(__name__)

DESCRIPTION = """
Decision-support platform for insurance document authenticity, fraud detection and verification.

**What this API does.** It combines forensic measurement, OCR and field extraction, deterministic
consistency rules, cross-document comparison, synthetic-media analysis and trusted-source
verification into an explainable evidence record, and hands the decision to a human investigator.

**What it does not do.** No endpoint returns a verdict on whether a document is genuine or
fraudulent. Findings carry a severity, a calibrated confidence, the evidence measured and the
detector plus model version that produced them. The risk score is a triage ranking, not a
probability of fraud. Verification results state whether they came from a production source or
from the bundled demo registry.
"""

TAGS = [
    {"name": "system", "description": "Health, readiness and configured capabilities."},
    {"name": "authentication", "description": "Sign-in, token rotation, roles and permissions."},
    {"name": "dashboard", "description": "Aggregated operational metrics."},
    {"name": "claims", "description": "Claim bundles, documents and the final human decision."},
    {"name": "documents", "description": "Upload, analysis, findings, review and file access."},
    {"name": "verification", "description": "Trusted-source verification (demo and production)."},
    {"name": "investigations", "description": "Investigation cases and notes."},
    {"name": "reports", "description": "Evidence report generation and PDF export."},
    {"name": "audit", "description": "Append-only audit trail and hash-chain verification."},
    {"name": "users", "description": "User administration and workload."},
    {"name": "administration", "description": "Rules, providers and system settings."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("DEBUG" if settings.debug else "INFO")
    logger.info(
        "api_starting",
        extra={"env": settings.app_env, "pipeline": PIPELINE_VERSION, "rules": RULES_VERSION,
               "storage": settings.storage_provider, "queue": settings.queue_mode},
    )
    yield
    logger.info("api_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=PIPELINE_VERSION,
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        contact={"name": "VeriDoc platform team"},
        license_info={"name": "Proprietary"},
    )

    if settings.trusted_host_list and settings.trusted_host_list != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        expose_headers=["X-Request-Id", "X-Document-SHA256", "X-Report-SHA256",
                        "Content-Disposition"],
        max_age=600,
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root():
        return {
            "name": settings.app_name,
            "api": settings.api_prefix,
            "docs": "/docs",
            "pipeline_version": PIPELINE_VERSION,
            "notice": ("Decision-support platform. Findings are probabilistic or rule-based "
                       "signals for human investigation, not verdicts."),
        }

    return app


app = create_app()
