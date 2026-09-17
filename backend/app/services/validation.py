"""Pre-ingest file validation.

Order matters: we sniff *content* before trusting the client-declared MIME type
or the filename extension, and we reject before a single byte is persisted
anywhere other than the quarantine-scoped temp buffer.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.errors import CorruptDocument, FileTooLarge, UnsupportedDocument
from app.core.logging import get_logger

logger = get_logger(__name__)

MAGIC = {
    b"%PDF-": ("application/pdf", "pdf"),
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
    b"II*\x00": ("image/tiff", "tif"),
    b"MM\x00*": ("image/tiff", "tif"),
}

EXTENSION_ALIASES = {"jpeg": "jpg", "tiff": "tif"}
_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._\- ()]+")


@dataclass(slots=True)
class ValidationResult:
    detected_mime: str
    normalized_extension: str
    page_count: int
    safe_filename: str
    size: int
    warnings: list[str] = field(default_factory=list)
    structural: dict = field(default_factory=dict)


def sanitize_filename(name: str) -> str:
    """Keep the original name for the audit record, but never trust it on disk."""
    name = (name or "document").replace("\x00", "").strip()
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    name = _FILENAME_SAFE.sub("_", name)
    return name[:240] or "document"


def sniff_mime(data: bytes) -> tuple[str | None, str | None]:
    head = data[:16]
    for magic, (mime, ext) in MAGIC.items():
        if head.startswith(magic):
            return mime, ext
    try:  # secondary opinion, optional dependency
        import magic as libmagic

        detected = libmagic.from_buffer(data[:4096], mime=True)
        if detected:
            return detected, None
    except Exception:
        pass
    return None, None


def validate_upload(
    data: bytes, original_filename: str, declared_mime: str | None
) -> ValidationResult:
    size = len(data)
    if size == 0:
        raise CorruptDocument("The uploaded file is empty (0 bytes).")
    if size > settings.max_upload_bytes:
        raise FileTooLarge(
            f"File is {size / 1048576:.1f} MB; the limit is {settings.max_upload_mb} MB."
        )

    safe_name = sanitize_filename(original_filename)
    claimed_ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    claimed_ext = EXTENSION_ALIASES.get(claimed_ext, claimed_ext)

    detected_mime, detected_ext = sniff_mime(data)
    warnings: list[str] = []

    if detected_mime is None or detected_mime.lower() not in settings.mime_list:
        raise UnsupportedDocument(
            "Only PDF, JPG/JPEG, PNG and TIFF documents can be analysed. "
            f"Detected content type: {detected_mime or 'unrecognised'}."
        )
    if claimed_ext and claimed_ext not in settings.extension_list:
        raise UnsupportedDocument(f"The extension '.{claimed_ext}' is not permitted.")
    if declared_mime and declared_mime.lower() != detected_mime.lower():
        warnings.append(
            f"Declared content type '{declared_mime}' does not match detected '{detected_mime}'."
        )
    normalized_ext = detected_ext or EXTENSION_ALIASES.get(claimed_ext, claimed_ext) or "bin"
    if claimed_ext and detected_ext and claimed_ext != detected_ext:
        warnings.append(
            f"File extension '.{claimed_ext}' disagrees with detected format '{detected_ext}'."
        )

    if detected_mime == "application/pdf":
        page_count, structural, pdf_warnings = _inspect_pdf(data)
    else:
        page_count, structural, pdf_warnings = _inspect_image(data, detected_mime)
    warnings.extend(pdf_warnings)

    if page_count > settings.max_page_count:
        raise UnsupportedDocument(
            f"Document has {page_count} pages; the analysis limit is {settings.max_page_count}."
        )

    return ValidationResult(
        detected_mime=detected_mime,
        normalized_extension=normalized_ext,
        page_count=page_count,
        safe_filename=safe_name,
        size=size,
        warnings=warnings,
        structural=structural,
    )


def _inspect_pdf(data: bytes) -> tuple[int, dict, list[str]]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    warnings: list[str] = []
    if not data.startswith(b"%PDF-"):
        offset = data[:4096].find(b"%PDF-")
        warnings.append(f"PDF header found at byte offset {offset} rather than 0 (polyglot risk).")
    if b"%%EOF" not in data[-4096:]:
        warnings.append("No %%EOF marker near end of file - the PDF may be truncated.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise CorruptDocument(
                    "The PDF is password protected. Please upload a decrypted copy."
                ) from None
        page_count = len(reader.pages)
        if page_count == 0:
            raise CorruptDocument("The PDF reports zero pages and cannot be analysed.")
        structural = {
            "eof_markers": data.count(b"%%EOF"),
            "startxref_markers": data.count(b"startxref"),
            "obj_count": data.count(b" obj"),
            "linearized": b"/Linearized" in data[:4096],
            "pdf_version": data[5:8].decode("latin-1", "ignore"),
        }
        return page_count, structural, warnings
    except CorruptDocument:
        raise
    except (PdfReadError, Exception) as exc:
        raise CorruptDocument(
            "The PDF structure could not be parsed. The file may be corrupt or truncated. "
            f"Parser said: {type(exc).__name__}."
        ) from exc


def _inspect_image(data: bytes, mime: str) -> tuple[int, dict, list[str]]:
    from PIL import Image, ImageFile

    ImageFile.LOAD_TRUNCATED_IMAGES = False
    warnings: list[str] = []
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            frames = getattr(img, "n_frames", 1)
            structural = {
                "format": img.format,
                "mode": img.mode,
                "width": img.width,
                "height": img.height,
                "frames": frames,
            }
            if img.width * img.height > 80_000_000:
                raise UnsupportedDocument(
                    "Image resolution exceeds the safe decoding limit (80 MP)."
                )
    except UnsupportedDocument:
        raise
    except Exception as exc:
        raise CorruptDocument(
            f"The image could not be decoded ({type(exc).__name__}). It may be corrupt."
        ) from exc

    if mime == "image/jpeg":
        eoi = data.rfind(b"\xff\xd9")
        if eoi != -1 and len(data) - eoi > 1024:
            warnings.append(
                f"{len(data) - eoi - 2} bytes of data follow the JPEG end-of-image marker."
            )
    if b"PK\x03\x04" in data[:2048]:
        warnings.append("Embedded ZIP signature detected near the file header (polyglot risk).")
    return structural.get("frames", 1), structural, warnings
