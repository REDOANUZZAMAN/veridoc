from __future__ import annotations

from app.core.config import settings
from app.services.ocr.base import OcrProvider
from app.services.ocr.demo_fixture import DemoFixtureProvider
from app.services.ocr.hybrid import HybridProvider
from app.services.ocr.pdf_text import PdfTextLayerProvider
from app.services.ocr.tesseract import TesseractProvider

REGISTRY: dict[str, type[OcrProvider]] = {
    "hybrid": HybridProvider,
    "tesseract": TesseractProvider,
    "pdf_text": PdfTextLayerProvider,
    "demo_fixture": DemoFixtureProvider,
}


def get_ocr_provider(key: str | None = None) -> OcrProvider:
    """Resolve the active OCR provider.

    Precedence: explicit argument > active DB provider_config > env default.
    """
    resolved = key or _from_db() or settings.ocr_provider
    cls = REGISTRY.get(resolved, HybridProvider)
    return cls()


def _from_db() -> str | None:
    try:
        from sqlalchemy import select

        from app.db.models.config import ProviderConfig
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            row = db.execute(
                select(ProviderConfig.key).where(
                    ProviderConfig.kind == "ocr", ProviderConfig.is_active.is_(True)
                )
            ).scalar_one_or_none()
            return row
    except Exception:
        return None


def list_ocr_providers() -> list[dict]:
    return [cls().describe() for cls in REGISTRY.values()]
