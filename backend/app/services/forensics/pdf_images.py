"""Embedded raster extraction for PDFs.

Why this exists: running ELA, noise-residual or compression analysis on a
*vector* PDF page render measures the renderer, not the document. Those metrics
only carry information when there is a real capture/compression history - which
in a PDF lives in the embedded raster objects (a scan, a pasted photograph, a
signature graphic).

So the pipeline analyses embedded rasters, and when a page carries a full-page
scan the image's pixel space is mapped onto the page render space, so a region
found in the scan is still clickable in the viewer.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

MIN_PIXELS = 100_000          # ignore icons, bullets and hairline graphics
FULL_PAGE_AREA_RATIO = 0.45   # image occupying most of the page = a scan


@dataclass(slots=True)
class EmbeddedRaster:
    page: int
    name: str
    data: bytes
    width: int
    height: int
    coord_scale: float
    covers_page: bool
    source_format: str
    filters: list[str]


def extract_embedded_rasters(
    pdf_bytes: bytes, page_sizes: dict[int, tuple[int, int]], *, page_limit: int = 12
) -> tuple[list[EmbeddedRaster], dict]:
    out: list[EmbeddedRaster] = []
    info: dict = {"pages_scanned": 0, "objects_seen": 0, "objects_analysable": 0, "skipped": []}
    try:
        import pikepdf
    except Exception as exc:  # pragma: no cover
        info["error"] = f"pikepdf unavailable: {exc}"
        return out, info

    try:
        with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                if index > page_limit:
                    break
                info["pages_scanned"] += 1
                resources = page.get("/Resources") or {}
                xobjects = resources.get("/XObject") or {}
                try:
                    items = dict(xobjects).items()
                except Exception:
                    continue
                render_w, render_h = page_sizes.get(index, (0, 0))
                for name, obj in items:
                    try:
                        if str(obj.get("/Subtype", "")) != "/Image":
                            continue
                        info["objects_seen"] += 1
                        width = int(obj.get("/Width", 0) or 0)
                        height = int(obj.get("/Height", 0) or 0)
                        if width * height < MIN_PIXELS:
                            info["skipped"].append(
                                {"name": str(name), "page": index,
                                 "reason": f"below {MIN_PIXELS} px analysis floor",
                                 "dimensions": [width, height]})
                            continue
                        image = pikepdf.PdfImage(obj)
                        pil = image.as_pil_image().convert("RGB")
                        buffer = io.BytesIO()
                        # Re-encode losslessly: the analysis needs pixels, and the
                        # original stream's own filter is reported separately.
                        pil.save(buffer, format="PNG")
                        filters = obj.get("/Filter")
                        filter_names = (
                            [str(f).lstrip("/") for f in filters] if isinstance(filters, list)
                            else ([str(filters).lstrip("/")] if filters is not None else [])
                        )
                        covers = False
                        scale = 1.0
                        if render_w and render_h:
                            area_ratio = (width * height) / float(render_w * render_h)
                            aspect_close = abs((width / max(height, 1)) -
                                               (render_w / max(render_h, 1))) < 0.12
                            covers = area_ratio >= FULL_PAGE_AREA_RATIO and aspect_close
                            if covers:
                                scale = render_w / float(width)
                        out.append(EmbeddedRaster(
                            page=index, name=str(name), data=buffer.getvalue(),
                            width=width, height=height, coord_scale=scale,
                            covers_page=covers,
                            source_format="+".join(filter_names) or "raw",
                            filters=filter_names,
                        ))
                        info["objects_analysable"] += 1
                    except Exception as exc:
                        info["skipped"].append({"name": str(name), "page": index,
                                                "reason": f"decode failed: {type(exc).__name__}"})
    except Exception as exc:
        logger.warning("embedded_raster_extraction_failed", extra={"detail": str(exc)[:160]})
        info["error"] = type(exc).__name__
    return out, info
