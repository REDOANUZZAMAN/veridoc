from __future__ import annotations

from app.core.errors import ProviderUnavailable
from app.core.logging import get_logger
from app.services.ocr.base import OcrPageResult, OcrProvider, OcrTarget
from app.services.ocr.pdf_text import PdfTextLayerProvider
from app.services.ocr.tesseract import TesseractProvider

logger = get_logger(__name__)

MIN_TEXT_LAYER_WORDS = 12


class HybridProvider(OcrProvider):
    """Default provider: exact text layer when the PDF has one, pixel OCR otherwise.

    Real claim bundles mix digitally generated invoices with phone photos of
    receipts. Using the embedded text layer where it exists keeps field
    extraction exact; scans fall through to Tesseract.
    """

    key = "hybrid"
    label = "Hybrid (PDF text layer -> Tesseract fallback)"
    version = "1.1"

    def __init__(self) -> None:
        self.text_layer = PdfTextLayerProvider()
        self.pixel = TesseractProvider()

    def available(self) -> tuple[bool, str]:
        t_ok, t_detail = self.pixel.available()
        p_ok, p_detail = self.text_layer.available()
        if not (t_ok or p_ok):
            return False, f"No OCR path available ({t_detail}; {p_detail})"
        return True, f"text-layer: {p_detail}; pixel: {t_detail}"

    def extract(self, target: OcrTarget) -> OcrPageResult:
        errors: list[str] = []
        if target.pdf_bytes:
            try:
                result = self.text_layer.extract(target)
                if result.word_count >= MIN_TEXT_LAYER_WORDS:
                    result.engine_detail["route"] = "pdf_text_layer"
                    return result
                errors.append(
                    f"text layer produced only {result.word_count} words - falling back to OCR"
                )
            except ProviderUnavailable as exc:
                errors.append(str(exc))
        try:
            result = self.pixel.extract(target)
            result.engine_detail["route"] = "pixel_ocr"
            if errors:
                result.engine_detail["fallback_reason"] = errors
            return result
        except ProviderUnavailable as exc:
            errors.append(str(exc))
            raise ProviderUnavailable("hybrid", "; ".join(errors)) from exc
