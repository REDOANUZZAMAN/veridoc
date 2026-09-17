"""OCR provider abstraction.

Providers receive an :class:`OcrTarget` that carries *both* the rasterised page
and (for PDFs) the original bytes, so a text-layer extractor and a pixel OCR
engine can implement the same interface. Swapping in AWS Textract, Google
Document AI or Azure Document Intelligence later means adding one class here -
nothing downstream changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class BBox:
    x: int
    y: int
    width: int
    height: int

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(slots=True)
class OcrWord:
    text: str
    confidence: float
    bbox: BBox
    line_index: int
    block_index: int = 0

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bbox": self.bbox.as_dict(),
            "line": self.line_index,
            "block": self.block_index,
        }


@dataclass(slots=True)
class OcrPageResult:
    page_number: int
    text: str
    words: list[OcrWord]
    mean_confidence: float
    provider: str
    provider_version: str
    duration_ms: int = 0
    status: str = "completed"
    error: str | None = None
    engine_detail: dict = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return len(self.words)

    def lines(self) -> list[list[OcrWord]]:
        grouped: dict[int, list[OcrWord]] = {}
        for w in self.words:
            grouped.setdefault(w.line_index, []).append(w)
        return [grouped[k] for k in sorted(grouped)]

    def line_texts(self) -> list[str]:
        return [" ".join(w.text for w in line) for line in self.lines()]


@dataclass(slots=True)
class OcrTarget:
    page_number: int
    image_bytes: bytes
    width: int
    height: int
    pdf_bytes: bytes | None = None
    dpi: int = 150
    language: str = "eng"
    has_text_layer: bool = False
    artifact_prefix: str | None = None


class OcrProvider(ABC):
    key: str = "abstract"
    label: str = "Abstract OCR provider"
    version: str = "0"
    is_demo: bool = False
    returns_bounding_boxes: bool = True

    def available(self) -> tuple[bool, str]:
        return True, "ready"

    @abstractmethod
    def extract(self, target: OcrTarget) -> OcrPageResult: ...

    def describe(self) -> dict:
        ok, detail = self.available()
        return {
            "key": self.key, "label": self.label, "version": self.version,
            "is_demo": self.is_demo, "bounding_boxes": self.returns_bounding_boxes,
            "available": ok, "detail": detail,
        }


def empty_result(page_number: int, provider: str, version: str, status: str, error: str) -> OcrPageResult:
    return OcrPageResult(
        page_number=page_number, text="", words=[], mean_confidence=0.0,
        provider=provider, provider_version=version, status=status, error=error,
    )
