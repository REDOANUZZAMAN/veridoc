from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import (
    PIPELINE_VERSION,
    RISK_WEIGHTS_VERSION,
    RULES_VERSION,
    settings,
)
from app.db.session import database_ready
from app.services.aigc.factory import list_aigc_providers
from app.services.ocr.factory import list_ocr_providers
from app.services.storage.factory import get_storage
from app.services.verification.factory import list_verification_providers
from app.workers.queue import queue_health

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness probe")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/ready", summary="Readiness probe with dependency status")
def ready() -> dict:
    db_ok = database_ready()
    storage = get_storage().health()
    queue = queue_health()
    ready_flag = db_ok and storage.get("status") != "unhealthy"
    return {
        "ready": ready_flag,
        "components": {
            "database": {"healthy": db_ok},
            "storage": storage,
            "queue": queue,
        },
        "versions": {
            "pipeline": PIPELINE_VERSION,
            "rules": RULES_VERSION,
            "risk_weights": RISK_WEIGHTS_VERSION,
        },
        "environment": settings.app_env,
        "demo_mode": settings.demo_mode,
    }


@router.get("/system/capabilities", summary="Configured providers and limits")
def capabilities() -> dict:
    return {
        "upload": {
            "max_size_mb": settings.max_upload_mb,
            "allowed_mime_types": settings.mime_list,
            "allowed_extensions": settings.extension_list,
            "max_pages": settings.max_page_count,
        },
        "providers": {
            "ocr": {"active": settings.ocr_provider, "available": list_ocr_providers()},
            "aigc": {"active": settings.aigc_provider, "available": list_aigc_providers()},
            "verification": {"active": settings.verification_provider,
                             "available": list_verification_providers()},
            "storage": {"active": settings.storage_provider},
            "malware": {"active": settings.malware_scanner},
        },
        "queue": {"mode": settings.queue_mode},
        "versions": {"pipeline": PIPELINE_VERSION, "rules": RULES_VERSION,
                     "risk_weights": RISK_WEIGHTS_VERSION},
        "privacy": {"retention_days": settings.retention_days,
                    "pii_log_redaction": settings.pii_log_redaction},
    }
