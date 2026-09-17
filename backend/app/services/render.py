"""Page rasterisation.

Every document - PDF or image - is normalised into one PNG per page stored in
the *artifacts* scope. Downstream stages (image forensics, AIGC, tampering
overlays) and the investigation viewer all read those renders, so they share a
single coordinate space: render pixels at ``render_dpi``.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from app.core.config import settings
from app.core.errors import CorruptDocument
from app.core.logging import get_logger
from app.services.storage.base import StorageProvider

logger = get_logger(__name__)

MAX_RENDER_EDGE = 2400
THUMB_EDGE = 320


@dataclass(slots=True)
class RenderedPage:
    page_number: int
    width: int
    height: int
    render_key: str
    thumb_key: str
    png_bytes: bytes
    dpi: int


def render_document(
    data: bytes, mime: str, artifact_prefix: str, storage: StorageProvider, page_limit: int | None = None
) -> list[RenderedPage]:
    if mime == "application/pdf":
        images = _render_pdf(data, page_limit)
    else:
        images = _render_image(data, page_limit)
    if not images:
        raise CorruptDocument("No renderable pages were produced from this document.")

    pages: list[RenderedPage] = []
    for idx, img in enumerate(images, start=1):
        img = _downscale(img)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png = buf.getvalue()
        render_key = f"{artifact_prefix}/pages/page-{idx:03d}.png"
        storage.write("artifacts", render_key, png, "image/png")

        thumb = img.copy()
        thumb.thumbnail((THUMB_EDGE, THUMB_EDGE))
        tbuf = io.BytesIO()
        thumb.save(tbuf, format="PNG", optimize=True)
        thumb_key = f"{artifact_prefix}/pages/thumb-{idx:03d}.png"
        storage.write("artifacts", thumb_key, tbuf.getvalue(), "image/png")

        pages.append(
            RenderedPage(
                page_number=idx, width=img.width, height=img.height,
                render_key=render_key, thumb_key=thumb_key, png_bytes=png,
                dpi=settings.render_dpi,
            )
        )
    return pages


def _render_pdf(data: bytes, page_limit: int | None):
    try:
        from pdf2image import convert_from_bytes

        return convert_from_bytes(
            data, dpi=settings.render_dpi, fmt="png",
            last_page=page_limit or settings.max_page_count,
        )
    except Exception as exc:
        logger.warning("pdf_rasterise_failed_falling_back", extra={"detail": str(exc)[:200]})
        return _render_pdf_fallback(data, page_limit)


def _render_pdf_fallback(data: bytes, page_limit: int | None):
    """If poppler is missing, emit blank canvases sized from the PDF MediaBox.

    Analysis that needs pixels will report ``unavailable`` for those stages
    rather than failing the whole run - text, metadata and structural forensics
    still work from the PDF itself.
    """
    from PIL import Image
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception:
        return []
    out = []
    scale = settings.render_dpi / 72.0
    for page in reader.pages[: page_limit or settings.max_page_count]:
        try:
            box = page.mediabox
            w = max(int(float(box.width) * scale), 100)
            h = max(int(float(box.height) * scale), 100)
        except Exception:
            w, h = 1275, 1650
        out.append(Image.new("RGB", (min(w, MAX_RENDER_EDGE), min(h, MAX_RENDER_EDGE)), "white"))
    return out


def _render_image(data: bytes, page_limit: int | None):
    from PIL import Image, ImageSequence

    out = []
    with Image.open(io.BytesIO(data)) as img:
        for frame in ImageSequence.Iterator(img):
            out.append(frame.convert("RGB"))
            if page_limit and len(out) >= page_limit:
                break
            if len(out) >= settings.max_page_count:
                break
    return out


def _downscale(img):
    from PIL import Image

    if max(img.width, img.height) <= MAX_RENDER_EDGE:
        return img.convert("RGB") if img.mode != "RGB" else img
    ratio = MAX_RENDER_EDGE / max(img.width, img.height)
    return img.convert("RGB").resize(
        (int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS
    )
