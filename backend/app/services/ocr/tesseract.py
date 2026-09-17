from __future__ import annotations

import io
import shutil
import time

from app.core.errors import ProviderUnavailable
from app.core.logging import get_logger
from app.services.ocr.base import BBox, OcrPageResult, OcrProvider, OcrTarget, OcrWord

logger = get_logger(__name__)


class TesseractProvider(OcrProvider):
    """Local Tesseract OCR via pytesseract's TSV output (words + boxes + conf)."""

    key = "tesseract"
    label = "Tesseract OCR (local)"

    def __init__(self, psm: int = 3, oem: int = 3):
        self.psm, self.oem = psm, oem
        self._version: str | None = None

    @property
    def version(self) -> str:  # type: ignore[override]
        if self._version is None:
            try:
                import pytesseract

                self._version = str(pytesseract.get_tesseract_version()).split()[0]
            except Exception:
                self._version = "unavailable"
        return self._version

    def available(self) -> tuple[bool, str]:
        if shutil.which("tesseract") is None:
            return False, "The 'tesseract' binary is not on PATH."
        try:
            import pytesseract  # noqa: F401
        except Exception as exc:
            return False, f"pytesseract import failed: {exc}"
        return True, f"tesseract {self.version}"

    def extract(self, target: OcrTarget) -> OcrPageResult:
        ok, detail = self.available()
        if not ok:
            raise ProviderUnavailable("tesseract", detail)

        import pytesseract
        from PIL import Image

        started = time.perf_counter()
        try:
            with Image.open(io.BytesIO(target.image_bytes)) as img:
                img = img.convert("L")
                data = pytesseract.image_to_data(
                    img, lang=target.language,
                    config=f"--oem {self.oem} --psm {self.psm}",
                    output_type=pytesseract.Output.DICT,
                )
        except Exception as exc:
            raise ProviderUnavailable("tesseract", f"OCR execution failed: {exc}") from exc

        words: list[OcrWord] = []
        line_map: dict[tuple[int, int, int], int] = {}
        for i, raw in enumerate(data.get("text", [])):
            text = (raw or "").strip()
            conf = float(data["conf"][i]) if data["conf"][i] not in ("-1", -1, "") else -1.0
            if not text or conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            line_index = line_map.setdefault(key, len(line_map))
            words.append(
                OcrWord(
                    text=text,
                    confidence=conf / 100.0,
                    bbox=BBox(int(data["left"][i]), int(data["top"][i]),
                              int(data["width"][i]), int(data["height"][i])),
                    line_index=line_index,
                    block_index=int(data["block_num"][i]),
                )
            )
        mean_conf = sum(w.confidence for w in words) / len(words) if words else 0.0
        text_out = _compose_text(words)
        return OcrPageResult(
            page_number=target.page_number, text=text_out, words=words,
            mean_confidence=mean_conf, provider=self.key, provider_version=self.version,
            duration_ms=int((time.perf_counter() - started) * 1000),
            status="completed" if words else "empty",
            error=None if words else "No text was recognised on this page.",
            engine_detail={"psm": self.psm, "oem": self.oem, "language": target.language},
        )


def _compose_text(words: list[OcrWord]) -> str:
    lines: dict[int, list[OcrWord]] = {}
    for w in words:
        lines.setdefault(w.line_index, []).append(w)
    out = []
    for k in sorted(lines):
        row = sorted(lines[k], key=lambda w: w.bbox.x)
        out.append(" ".join(w.text for w in row))
    return "\n".join(out)
