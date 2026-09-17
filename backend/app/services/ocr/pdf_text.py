from __future__ import annotations

import io
import time

from app.core.errors import ProviderUnavailable
from app.services.ocr.base import BBox, OcrPageResult, OcrProvider, OcrTarget, OcrWord


class PdfTextLayerProvider(OcrProvider):
    """Extracts the embedded text layer of a digital PDF.

    This is not OCR - it is exact character data - so confidence is reported as
    0.995 rather than a recognition score, and coordinates are converted from
    PDF points into render-pixel space so highlights line up with the viewer.
    """

    key = "pdf_text"
    label = "PDF text-layer extractor (pdfplumber)"
    version = "1.0"

    def available(self) -> tuple[bool, str]:
        try:
            import pdfplumber  # noqa: F401
        except Exception as exc:
            return False, f"pdfplumber unavailable: {exc}"
        return True, "ready"

    def extract(self, target: OcrTarget) -> OcrPageResult:
        if not target.pdf_bytes:
            raise ProviderUnavailable("pdf_text", "No PDF payload for text-layer extraction.")
        import pdfplumber

        started = time.perf_counter()
        words: list[OcrWord] = []
        try:
            with pdfplumber.open(io.BytesIO(target.pdf_bytes)) as pdf:
                if target.page_number > len(pdf.pages):
                    raise ProviderUnavailable("pdf_text", "Page index beyond document length.")
                page = pdf.pages[target.page_number - 1]
                scale_x = target.width / float(page.width or 1)
                scale_y = target.height / float(page.height or 1)
                raw_words = page.extract_words(
                    use_text_flow=False, keep_blank_chars=False,
                    extra_attrs=["fontname", "size"],
                )
                rows: list[tuple[float, list[dict]]] = []
                for w in raw_words:
                    top = round(float(w["top"]), 1)
                    for row_top, bucket in rows:
                        if abs(row_top - top) <= max(2.0, float(w.get("size", 10)) * 0.4):
                            bucket.append(w)
                            break
                    else:
                        rows.append((top, [w]))
                rows.sort(key=lambda r: r[0])
                for line_index, (_, bucket) in enumerate(rows):
                    for w in sorted(bucket, key=lambda x: x["x0"]):
                        words.append(
                            OcrWord(
                                text=w["text"],
                                confidence=0.995,
                                bbox=BBox(
                                    int(float(w["x0"]) * scale_x),
                                    int(float(w["top"]) * scale_y),
                                    max(int((float(w["x1"]) - float(w["x0"])) * scale_x), 1),
                                    max(int((float(w["bottom"]) - float(w["top"])) * scale_y), 1),
                                ),
                                line_index=line_index,
                            )
                        )
                fonts = sorted({w.get("fontname", "?") for w in raw_words})
                sizes = sorted({round(float(w.get("size", 0)), 1) for w in raw_words})
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable("pdf_text", f"Text-layer extraction failed: {exc}") from exc

        text = "\n".join(
            " ".join(w.text for w in sorted(group, key=lambda x: x.bbox.x))
            for group in _group_lines(words)
        )
        return OcrPageResult(
            page_number=target.page_number, text=text, words=words,
            mean_confidence=0.995 if words else 0.0,
            provider=self.key, provider_version=self.version,
            duration_ms=int((time.perf_counter() - started) * 1000),
            status="completed" if words else "empty",
            error=None if words else "This page has no embedded text layer (likely a scan).",
            engine_detail={"fonts": fonts, "font_sizes": sizes, "extraction": "embedded_text"},
        )


def _group_lines(words: list[OcrWord]) -> list[list[OcrWord]]:
    lines: dict[int, list[OcrWord]] = {}
    for w in words:
        lines.setdefault(w.line_index, []).append(w)
    return [lines[k] for k in sorted(lines)]
