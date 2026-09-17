"""PDF structural and metadata forensics.

All signals are measured from the file itself (docinfo, XMP, xref generations,
font resources, embedded objects, annotations, byte-level markers). Nothing is
inferred from a model, so every finding carries the raw measurement as evidence.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timedelta, timezone

from app.core.logging import get_logger
from app.db.enums import FindingCategory, Severity
from app.services.forensics.base import MetadataEntry, RawFinding, clamp

logger = get_logger(__name__)

DETECTOR = "pdf-structure-forensics"
DETECTOR_VERSION = "1.5.0"

# Software whose presence in /Producer or /Creator says something about how the
# document came to exist. Categorised, never treated as proof of anything.
SOFTWARE_CLASSES: list[tuple[str, str, str]] = [
    ("photoshop", "image_editor", "Adobe Photoshop"),
    ("gimp", "image_editor", "GIMP"),
    ("illustrator", "image_editor", "Adobe Illustrator"),
    ("inkscape", "image_editor", "Inkscape"),
    ("canva", "design_tool", "Canva"),
    ("figma", "design_tool", "Figma"),
    ("itext", "pdf_manipulation", "iText"),
    ("pdfsharp", "pdf_manipulation", "PDFsharp"),
    ("ghostscript", "pdf_manipulation", "Ghostscript"),
    ("qpdf", "pdf_manipulation", "qpdf"),
    ("pdftk", "pdf_manipulation", "pdftk"),
    ("pypdf", "pdf_manipulation", "pypdf"),
    ("pikepdf", "pdf_manipulation", "pikepdf"),
    ("foxit", "pdf_editor", "Foxit"),
    ("nitro", "pdf_editor", "Nitro PDF"),
    ("acrobat", "pdf_editor", "Adobe Acrobat"),
    ("pdf-xchange", "pdf_editor", "PDF-XChange"),
    ("smallpdf", "online_editor", "Smallpdf"),
    ("ilovepdf", "online_editor", "iLovePDF"),
    ("sejda", "online_editor", "Sejda"),
    ("reportlab", "generator", "ReportLab"),
    ("tcpdf", "generator", "TCPDF"),
    ("fpdf", "generator", "FPDF"),
    ("wkhtmltopdf", "generator", "wkhtmltopdf"),
    ("chromium", "generator", "Chromium print-to-PDF"),
    ("skia", "generator", "Skia/Chrome print-to-PDF"),
    ("word", "office_suite", "Microsoft Word"),
    ("excel", "office_suite", "Microsoft Excel"),
    ("libreoffice", "office_suite", "LibreOffice"),
    ("openoffice", "office_suite", "OpenOffice"),
    ("quickbooks", "accounting", "QuickBooks"),
    ("sap", "accounting", "SAP"),
    ("scanner", "scanner", "Scanner firmware"),
    ("epson", "scanner", "Epson scanner"),
    ("canon", "scanner", "Canon scanner"),
    ("hp ", "scanner", "HP scanner"),
]

HIGH_CONCERN_CLASSES = {"image_editor", "design_tool", "online_editor"}
MEDIUM_CONCERN_CLASSES = {"pdf_manipulation", "pdf_editor"}


def parse_pdf_date(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(?:([+\-Z])(\d{2})'?(\d{2})?)?", raw)
    if not m:
        return None
    y, mo, d, h, mi, s, tzs, tzh, tzm = m.groups()
    try:
        dt = datetime(
            int(y), int(mo or 1), int(d or 1), int(h or 0), int(mi or 0), min(int(s or 0), 59)
        )
    except ValueError:
        return None
    if tzs and tzs != "Z":
        offset = timedelta(hours=int(tzh or 0), minutes=int(tzm or 0))
        dt = dt.replace(tzinfo=timezone(offset if tzs == "+" else -offset))
    else:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def classify_software(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    low = value.lower()
    for needle, klass, label in SOFTWARE_CLASSES:
        if needle in low:
            return klass, label
    return "unknown", value.strip()[:80]


def analyze_pdf(data: bytes) -> tuple[list[MetadataEntry], list[RawFinding], dict]:
    metadata: list[MetadataEntry] = []
    findings: list[RawFinding] = []
    structure: dict = {}

    byte_structure = _byte_level(data)
    structure.update(byte_structure)

    info: dict = {}
    xmp: dict = {}
    page_details: list[dict] = []

    try:
        import pikepdf

        with pikepdf.open(io.BytesIO(data)) as pdf:
            structure["pdf_version"] = str(pdf.pdf_version)
            structure["object_count"] = len(pdf.objects)
            structure["page_count"] = len(pdf.pages)
            structure["is_encrypted"] = bool(pdf.is_encrypted)
            structure["is_linearized"] = bool(getattr(pdf, "is_linearized", False))

            try:
                info = {str(k): str(v) for k, v in dict(pdf.docinfo or {}).items()}
            except Exception:
                info = {}
            try:
                with pdf.open_metadata() as meta:
                    xmp = {str(k): str(v) for k, v in dict(meta).items()}
            except Exception:
                xmp = {}

            root = pdf.Root
            structure["has_acroform"] = "/AcroForm" in root
            structure["has_embedded_files"] = bool(
                "/Names" in root and "/EmbeddedFiles" in (root.Names or {})
            )
            structure["has_javascript"] = bool(
                "/Names" in root and "/JavaScript" in (root.Names or {})
            ) or "/JS" in str(root.get("/OpenAction", ""))
            structure["has_open_action"] = "/OpenAction" in root

            for index, page in enumerate(pdf.pages, start=1):
                page_details.append(_page_detail(page, index))
    except Exception as exc:
        logger.warning("pikepdf_inspect_failed", extra={"detail": str(exc)[:200]})
        structure["inspection_error"] = f"{type(exc).__name__}"
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data), strict=False)
            info = {str(k): str(v) for k, v in (reader.metadata or {}).items()}
            structure.setdefault("page_count", len(reader.pages))
        except Exception:
            pass

    structure["pages"] = page_details

    # --- metadata table -------------------------------------------------------
    created = parse_pdf_date(info.get("/CreationDate"))
    modified = parse_pdf_date(info.get("/ModDate"))
    producer = info.get("/Producer")
    creator = info.get("/Creator")

    for key, value in info.items():
        metadata.append(MetadataEntry("pdf_info", key.lstrip("/"), str(value)[:400]))
    for key, value in xmp.items():
        metadata.append(MetadataEntry("xmp", key[:120], str(value)[:400]))
    for key in ("pdf_version", "object_count", "page_count", "is_encrypted", "is_linearized",
                "eof_markers", "startxref_markers", "incremental_updates", "has_acroform",
                "has_embedded_files", "has_javascript", "has_open_action", "object_streams"):
        if key in structure:
            metadata.append(MetadataEntry("structure", key, str(structure[key])))

    # --- findings -------------------------------------------------------------
    findings.extend(_date_findings(created, modified, metadata))
    findings.extend(_software_findings(producer, creator, metadata))
    findings.extend(_revision_findings(structure, metadata))
    findings.extend(_missing_metadata_findings(info, structure))
    findings.extend(_font_findings(page_details))
    findings.extend(_image_object_findings(page_details))
    findings.extend(_annotation_findings(page_details))
    findings.extend(_active_content_findings(structure))

    structure["metadata_summary"] = {
        "producer": producer, "creator": creator,
        "created": created.isoformat() if created else None,
        "modified": modified.isoformat() if modified else None,
    }
    return metadata, findings, structure


def _byte_level(data: bytes) -> dict:
    eof = data.count(b"%%EOF")
    startxref = data.count(b"startxref")
    prev_refs = len(re.findall(rb"/Prev\s+\d+", data))
    return {
        "eof_markers": eof,
        "startxref_markers": startxref,
        "incremental_updates": max(0, max(eof, startxref) - 1),
        "xref_prev_references": prev_refs,
        "object_streams": data.count(b"/ObjStm"),
        "file_size": len(data),
        "trailing_bytes_after_last_eof": max(0, len(data) - (data.rfind(b"%%EOF") + 5)),
    }


def _page_detail(page, index: int) -> dict:
    detail: dict = {"page": index, "fonts": [], "images": [], "annotations": []}
    try:
        box = page.get("/MediaBox")
        if box is not None:
            detail["media_box"] = [float(v) for v in box]
    except Exception:
        pass
    try:
        detail["rotation"] = int(page.get("/Rotate", 0) or 0)
    except Exception:
        detail["rotation"] = 0

    resources = page.get("/Resources") or {}
    fonts = resources.get("/Font") or {}
    try:
        for name, font in dict(fonts).items():
            base = str(font.get("/BaseFont", "unknown"))
            subtype = str(font.get("/Subtype", "unknown"))
            descriptor = font.get("/FontDescriptor") or {}
            if not descriptor and font.get("/DescendantFonts"):
                try:
                    descriptor = dict(font.DescendantFonts[0]).get("/FontDescriptor") or {}
                except Exception:
                    descriptor = {}
            embedded = any(
                k in (descriptor or {}) for k in ("/FontFile", "/FontFile2", "/FontFile3")
            )
            detail["fonts"].append({
                "name": str(name), "base_font": base.lstrip("/"), "subtype": subtype.lstrip("/"),
                "embedded": bool(embedded),
            })
    except Exception:
        pass

    xobjects = resources.get("/XObject") or {}
    try:
        for name, xobj in dict(xobjects).items():
            if str(xobj.get("/Subtype", "")) != "/Image":
                continue
            filters = xobj.get("/Filter")
            filt = [str(f).lstrip("/") for f in (filters if isinstance(filters, list) else [filters])] \
                if filters is not None else []
            detail["images"].append({
                "name": str(name),
                "width": int(xobj.get("/Width", 0) or 0),
                "height": int(xobj.get("/Height", 0) or 0),
                "bits_per_component": int(xobj.get("/BitsPerComponent", 0) or 0),
                "colorspace": str(xobj.get("/ColorSpace", "unknown"))[:60],
                "filters": filt,
                "has_soft_mask": "/SMask" in xobj,
            })
    except Exception:
        pass

    annots = page.get("/Annots")
    try:
        if annots is not None:
            for annot in annots:
                detail["annotations"].append({
                    "subtype": str(annot.get("/Subtype", "unknown")).lstrip("/"),
                    "rect": [float(v) for v in (annot.get("/Rect") or [])],
                    "has_appearance": "/AP" in annot,
                    "contents": str(annot.get("/Contents", ""))[:80],
                })
    except Exception:
        pass
    return detail


def _date_findings(created, modified, metadata: list[MetadataEntry]) -> list[RawFinding]:
    out: list[RawFinding] = []
    now = datetime.now(timezone.utc)
    if created and modified:
        delta = modified - created
        if delta.total_seconds() < -60:
            out.append(RawFinding(
                code="PDF_MODDATE_BEFORE_CREATION", category=FindingCategory.METADATA,
                severity=Severity.HIGH,
                title="Modification date precedes creation date",
                description=("The document reports being modified before it was created, which "
                             "cannot happen in normal document workflows and is typical of "
                             "metadata that has been rewritten by an editing tool."),
                confidence=0.88, detector=DETECTOR, model_version=DETECTOR_VERSION,
                evidence={"creation_date": created.isoformat(), "mod_date": modified.isoformat(),
                          "difference_seconds": int(delta.total_seconds())},
                recommendation="Ask the provider for the source document and compare metadata.",
            ))
            _mark(metadata, "ModDate", "Earlier than CreationDate")
        elif delta.total_seconds() > 86400:
            days = delta.days
            conf = clamp(0.45 + min(days, 120) / 400.0, 0.45, 0.8)
            out.append(RawFinding(
                code="PDF_EDITED_AFTER_CREATION", category=FindingCategory.METADATA,
                severity=Severity.MEDIUM if days >= 7 else Severity.LOW,
                title=f"Document modified {days} day(s) after creation",
                description=("The PDF was saved again well after it was first produced. This is "
                             "common for legitimate re-issues, but for a transactional document "
                             "such as an invoice it is worth confirming with the issuer."),
                confidence=conf, detector=DETECTOR, model_version=DETECTOR_VERSION,
                evidence={"creation_date": created.isoformat(), "mod_date": modified.isoformat(),
                          "days_between": days},
                recommendation="Confirm whether the issuer re-issued this document.",
            ))
            _mark(metadata, "ModDate", f"{days} days after CreationDate")
    for label, value in (("CreationDate", created), ("ModDate", modified)):
        if value and value > now + timedelta(days=1):
            out.append(RawFinding(
                code="PDF_FUTURE_TIMESTAMP", category=FindingCategory.METADATA,
                severity=Severity.MEDIUM,
                title=f"{label} is in the future",
                description=(f"The {label} metadata value is later than the current server time, "
                             "which usually indicates an incorrect system clock or a manually "
                             "edited timestamp."),
                confidence=0.7, detector=DETECTOR, model_version=DETECTOR_VERSION,
                evidence={label: value.isoformat(), "server_time": now.isoformat()},
            ))
            _mark(metadata, label, "Timestamp in the future")
    return out


def _software_findings(producer, creator, metadata: list[MetadataEntry]) -> list[RawFinding]:
    out: list[RawFinding] = []
    p_class, p_label = classify_software(producer)
    c_class, c_label = classify_software(creator)

    for value, klass, label, field_name in (
        (producer, p_class, p_label, "Producer"), (creator, c_class, c_label, "Creator")
    ):
        if not value or not klass:
            continue
        if klass in HIGH_CONCERN_CLASSES:
            out.append(RawFinding(
                code="PDF_IMAGE_EDITOR_PRODUCER", category=FindingCategory.METADATA,
                severity=Severity.HIGH,
                title=f"{field_name} reports an image/design editor: {label}",
                description=(f"The PDF declares it was produced by {label}, a raster or design "
                             "editing tool. Transactional documents are normally exported by "
                             "accounting, hospital or print systems. This does not prove editing, "
                             "but it is an anomaly worth resolving with the issuer."),
                confidence=0.78, detector=DETECTOR, model_version=DETECTOR_VERSION,
                evidence={field_name.lower(): value, "software_class": klass},
                recommendation="Request the original export from the issuing system.",
            ))
            _mark(metadata, field_name, f"{label} ({klass})")
        elif klass in MEDIUM_CONCERN_CLASSES:
            out.append(RawFinding(
                code="PDF_MANIPULATION_TOOLING", category=FindingCategory.METADATA,
                severity=Severity.LOW,
                title=f"{field_name} reports PDF manipulation tooling: {label}",
                description=(f"{label} is commonly used to merge, split or re-save PDFs. Many "
                             "legitimate document pipelines use it, so treat this as context "
                             "rather than a concern on its own."),
                confidence=0.5, detector=DETECTOR, model_version=DETECTOR_VERSION,
                evidence={field_name.lower(): value, "software_class": klass},
            ))
            _mark(metadata, field_name, f"{label} ({klass})")

    if producer and creator:
        if p_class and c_class and p_class != c_class and {p_class, c_class} & (
            HIGH_CONCERN_CLASSES | MEDIUM_CONCERN_CLASSES
        ):
            out.append(RawFinding(
                code="PDF_PRODUCER_CREATOR_MISMATCH", category=FindingCategory.METADATA,
                severity=Severity.LOW,
                title="Creator and Producer belong to different software families",
                description=(f"Created with {c_label} ({c_class}) but produced by {p_label} "
                             f"({p_class}). This pattern appears when a document is exported by "
                             "one tool and then re-saved by another."),
                confidence=0.55, detector=DETECTOR, model_version=DETECTOR_VERSION,
                evidence={"creator": creator, "producer": producer,
                          "creator_class": c_class, "producer_class": p_class},
            ))
    return out


def _revision_findings(structure: dict, metadata: list[MetadataEntry]) -> list[RawFinding]:
    out: list[RawFinding] = []
    increments = int(structure.get("incremental_updates", 0) or 0)
    if increments >= 1:
        conf = clamp(0.55 + 0.12 * min(increments, 3), 0.55, 0.9)
        out.append(RawFinding(
            code="PDF_INCREMENTAL_UPDATE", category=FindingCategory.FORENSICS,
            severity=Severity.MEDIUM if increments >= 2 else Severity.LOW,
            title=f"{increments} incremental update(s) detected in the PDF body",
            description=("The file contains more than one cross-reference generation, meaning "
                         "content was appended after the original save. Incremental updates are "
                         "used legitimately for signatures and form filling, and also by tools "
                         "that overwrite objects such as text or images."),
            confidence=conf, detector=DETECTOR, model_version=DETECTOR_VERSION,
            evidence={"eof_markers": structure.get("eof_markers"),
                      "startxref_markers": structure.get("startxref_markers"),
                      "xref_prev_references": structure.get("xref_prev_references"),
                      "incremental_updates": increments},
            recommendation="Compare the first revision against the final rendering.",
            extras={"signal_group": "pdf"},
        ))
        _mark(metadata, "incremental_updates", f"{increments} revision generation(s)")
    trailing = int(structure.get("trailing_bytes_after_last_eof", 0) or 0)
    if trailing > 1024:
        out.append(RawFinding(
            code="PDF_TRAILING_DATA", category=FindingCategory.FORENSICS,
            severity=Severity.MEDIUM,
            title=f"{trailing} bytes present after the final %%EOF marker",
            description=("Data after the last end-of-file marker is ignored by most viewers but "
                         "can carry appended content or an older revision of the document."),
            confidence=0.6, detector=DETECTOR, model_version=DETECTOR_VERSION,
            evidence={"trailing_bytes": trailing},
            extras={"signal_group": "pdf"},
        ))
    return out


def _missing_metadata_findings(info: dict, structure: dict) -> list[RawFinding]:
    out: list[RawFinding] = []
    if not info:
        out.append(RawFinding(
            code="PDF_METADATA_ABSENT", category=FindingCategory.METADATA,
            severity=Severity.LOW,
            title="Document information dictionary is empty",
            description=("The PDF carries no /Info metadata at all. Some generators omit it, "
                         "and some tools strip it deliberately when re-saving a document."),
            confidence=0.45, detector=DETECTOR, model_version=DETECTOR_VERSION,
            evidence={"info_keys": []},
        ))
    elif "/Producer" not in info and "/Creator" not in info:
        out.append(RawFinding(
            code="PDF_PRODUCER_ABSENT", category=FindingCategory.METADATA,
            severity=Severity.LOW,
            title="No Producer or Creator recorded",
            description=("Neither /Producer nor /Creator is present, so the originating software "
                         "cannot be established from metadata."),
            confidence=0.42, detector=DETECTOR, model_version=DETECTOR_VERSION,
            evidence={"info_keys": sorted(info.keys())},
        ))
    return out


def _font_findings(pages: list[dict]) -> list[RawFinding]:
    out: list[RawFinding] = []
    for page in pages:
        fonts = page.get("fonts") or []
        if not fonts:
            continue
        bases = {f["base_font"].split("+")[-1] for f in fonts}
        non_embedded = [f for f in fonts if not f["embedded"]]
        if len(bases) >= 6:
            out.append(RawFinding(
                code="PDF_FONT_DIVERSITY", category=FindingCategory.FORENSICS,
                severity=Severity.LOW,
                title=f"{len(bases)} distinct typefaces on page {page['page']}",
                description=("A high number of distinct typefaces on one page can indicate "
                             "content assembled from multiple sources, though rich templates "
                             "legitimately use several fonts."),
                confidence=clamp(0.4 + 0.05 * (len(bases) - 5), 0.4, 0.7),
                detector=DETECTOR, model_version=DETECTOR_VERSION, page=page["page"],
                evidence={"fonts": sorted(bases)}, extras={"signal_group": "pdf"},
            ))
        if non_embedded and len(non_embedded) != len(fonts):
            out.append(RawFinding(
                code="PDF_MIXED_FONT_EMBEDDING", category=FindingCategory.FORENSICS,
                severity=Severity.MEDIUM,
                title=f"Page {page['page']} mixes embedded and non-embedded fonts",
                description=("Some text on this page uses fonts embedded in the file while other "
                             "text references system fonts. Text added to an existing PDF by a "
                             "different tool frequently shows this pattern."),
                confidence=0.62, detector=DETECTOR, model_version=DETECTOR_VERSION,
                page=page["page"],
                evidence={"non_embedded": [f["base_font"] for f in non_embedded],
                          "embedded": [f["base_font"] for f in fonts if f["embedded"]]},
                recommendation="Inspect the non-embedded text regions in the viewer.",
                extras={"signal_group": "pdf"},
            ))
    return out


def _image_object_findings(pages: list[dict]) -> list[RawFinding]:
    out: list[RawFinding] = []
    for page in pages:
        images = page.get("images") or []
        if len(images) < 2:
            continue
        filters = {tuple(i["filters"]) for i in images}
        depths = {i["bits_per_component"] for i in images if i["bits_per_component"]}
        if len(filters) > 1:
            out.append(RawFinding(
                code="PDF_MIXED_IMAGE_COMPRESSION", category=FindingCategory.FORENSICS,
                severity=Severity.MEDIUM,
                title=f"Page {page['page']} embeds images with different compression filters",
                description=("Embedded raster objects on the same page use different compression "
                             "pipelines (for example one JPEG and one lossless object). A pasted "
                             "region added over a scan often arrives with its own encoding."),
                confidence=0.6, detector=DETECTOR, model_version=DETECTOR_VERSION,
                page=page["page"],
                evidence={"filters": ["+".join(f) or "none" for f in filters],
                          "image_count": len(images),
                          "images": images[:8]},
                recommendation="Review the embedded image inventory and the page render.",
                extras={"signal_group": "pdf"},
            ))
        small_overlays = [
            i for i in images
            if 0 < i["width"] * i["height"] < 90_000 and i["has_soft_mask"]
        ]
        if small_overlays:
            out.append(RawFinding(
                code="PDF_MASKED_IMAGE_OVERLAY", category=FindingCategory.FORENSICS,
                severity=Severity.MEDIUM,
                title=f"{len(small_overlays)} small masked image overlay(s) on page {page['page']}",
                description=("Small images carrying a soft mask are typically used to place a "
                             "graphic transparently over existing content - the mechanism used "
                             "for stamps and signatures, legitimate or otherwise."),
                confidence=0.58, detector=DETECTOR, model_version=DETECTOR_VERSION,
                page=page["page"], evidence={"overlays": small_overlays[:6]},
                extras={"signal_group": "pdf"},
            ))
        if len(depths) > 1:
            out.append(RawFinding(
                code="PDF_MIXED_BIT_DEPTH", category=FindingCategory.FORENSICS,
                severity=Severity.LOW,
                title=f"Embedded images on page {page['page']} use different bit depths",
                description="Mixed bits-per-component values suggest images from different sources.",
                confidence=0.45, detector=DETECTOR, model_version=DETECTOR_VERSION,
                page=page["page"], evidence={"bit_depths": sorted(depths)},
                extras={"signal_group": "pdf"},
            ))
    return out


def _annotation_findings(pages: list[dict]) -> list[RawFinding]:
    out: list[RawFinding] = []
    for page in pages:
        annots = page.get("annotations") or []
        text_annots = [a for a in annots if a["subtype"] in {"FreeText", "Square", "Highlight",
                                                              "Stamp", "Ink", "Redact"}]
        if not text_annots:
            continue
        severity = Severity.MEDIUM if any(a["subtype"] in {"FreeText", "Redact", "Stamp"}
                                          for a in text_annots) else Severity.LOW
        out.append(RawFinding(
            code="PDF_CONTENT_ANNOTATIONS", category=FindingCategory.FORENSICS,
            severity=severity,
            title=f"{len(text_annots)} content annotation(s) overlay page {page['page']}",
            description=("Annotations such as FreeText, Stamp or Redact draw on top of the page "
                         "without changing the underlying content stream. A value can therefore "
                         "appear different to a reader than it is in the document body."),
            confidence=0.72, detector=DETECTOR, model_version=DETECTOR_VERSION,
            page=page["page"],
            evidence={"annotations": text_annots[:8]},
            recommendation="Compare the flattened render against the underlying text layer.",
            extras={"signal_group": "pdf"},
        ))
    return out


def _active_content_findings(structure: dict) -> list[RawFinding]:
    out: list[RawFinding] = []
    if structure.get("has_javascript"):
        out.append(RawFinding(
            code="PDF_EMBEDDED_JAVASCRIPT", category=FindingCategory.SECURITY,
            severity=Severity.HIGH,
            title="PDF contains embedded JavaScript",
            description=("Script content in a claim document is unusual and is a security as well "
                         "as an integrity concern; scripts can alter what a form displays."),
            confidence=0.85, detector=DETECTOR, model_version=DETECTOR_VERSION,
            evidence={"has_javascript": True, "has_open_action": structure.get("has_open_action")},
            recommendation="Handle in an isolated viewer; request a flattened copy.",
            extras={"signal_group": "pdf"},
        ))
    if structure.get("has_embedded_files"):
        out.append(RawFinding(
            code="PDF_EMBEDDED_FILES", category=FindingCategory.SECURITY,
            severity=Severity.MEDIUM,
            title="PDF carries embedded file attachments",
            description="The document has file attachments that are not part of the visible pages.",
            confidence=0.7, detector=DETECTOR, model_version=DETECTOR_VERSION,
            evidence={"has_embedded_files": True}, extras={"signal_group": "pdf"},
        ))
    return out


def _mark(metadata: list[MetadataEntry], key: str, note: str) -> None:
    for entry in metadata:
        if entry.key.lstrip("/").lower() == key.lstrip("/").lower():
            entry.is_anomalous = True
            entry.note = note
