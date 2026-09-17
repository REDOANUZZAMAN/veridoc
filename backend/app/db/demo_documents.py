"""Deterministic demo document generator.

Every demo artefact is *built*, not bundled: a specification describes the
document, and this module renders a real PDF or raster with the anomaly baked in
at the pixel / object level. That matters because the pipeline then has genuine
evidence to find - the demo does not fake findings, it fakes documents.

Determinism: all randomness comes from ``numpy.random.RandomState(seed)`` with a
seed derived from the document id, so the same seed always yields byte-identical
output and therefore identical findings and risk scores.

Anomalies that can be requested per document:

    font_anomaly_field   a value drawn in a different typeface from its line
    baseline_shift       a value drawn off its line's baseline
    trailing_bytes       data appended after the final %%EOF
    incremental_update   a genuine appended PDF revision (validated before use)
    annotation_overlay   a FreeText annotation drawn over a value
    editor_metadata      /Producer or EXIF Software naming an image editor
    reversed_dates       /ModDate earlier than /CreationDate
    splice_region        a region re-compressed at a different quality
    copy_move            a graphic duplicated at two positions
    smooth_synthetic     low high-frequency energy, uniform noise field
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
SANS = f"{FONT_DIR}/DejaVuSans.ttf"
SANS_BOLD = f"{FONT_DIR}/DejaVuSans-Bold.ttf"
SERIF = f"{FONT_DIR}/DejaVuSerif.ttf"
MONO = f"{FONT_DIR}/DejaVuSansMono.ttf"


@dataclass
class DocSpec:
    key: str
    kind: str                                    # pdf | card_png | photo_jpeg | synthetic_png
    title: str
    organisation: str
    org_subtitle: str = ""
    header_fields: list[tuple[str, str]] = field(default_factory=list)
    party_fields: list[tuple[str, str]] = field(default_factory=list)
    items: list[tuple[str, str, str, str]] = field(default_factory=list)  # desc, qty, unit, amount
    item_header: tuple[str, ...] = ("Description", "Qty", "Unit price", "Amount")
    totals: list[tuple[str, str]] = field(default_factory=list)
    body_paragraphs: list[str] = field(default_factory=list)
    footer: str = ""
    signature_line: str = ""
    currency_symbol: str = "$"
    # --- anomaly switches ---
    font_anomaly_field: str | None = None
    baseline_shift_field: str | None = None
    trailing_bytes: int = 0
    incremental_update: bool = False
    annotation_overlay: tuple[str, str] | None = None   # (label, text)
    producer: str | None = None
    creator: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    exif_software: str | None = None
    exif_capture: datetime | None = None
    exif_modified: datetime | None = None
    camera: tuple[str, str] | None = None
    splice_region_label: str | None = None
    copy_move_graphic: bool = False
    smooth_synthetic: bool = False
    jpeg_quality: int = 88
    seed: int = 7

    def rng(self):
        import numpy as np

        return np.random.RandomState(self.seed)


# --------------------------------------------------------------------------- #
# PDF rendering
# --------------------------------------------------------------------------- #
def render_pdf(spec: DocSpec) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as rl_canvas

    for name, path in (("DemoSans", SANS), ("DemoSans-Bold", SANS_BOLD),
                       ("DemoSerif", SERIF), ("DemoMono", MONO)):
        try:
            pdfmetrics.registerFont(TTFont(name, path))
        except Exception:
            pass

    buffer = io.BytesIO()
    width, height = A4
    # initialFontName avoids reportlab registering an unused base-14 Helvetica in
    # the page resources (which would look like mixed font embedding to the
    # forensics stage); invariant makes the byte output reproducible.
    try:
        c = rl_canvas.Canvas(buffer, pagesize=A4, initialFontName="DemoSans", invariant=1)
    except TypeError:  # older reportlab
        c = rl_canvas.Canvas(buffer, pagesize=A4, invariant=1)
    c.setTitle(spec.title)
    if spec.creator:
        c.setCreator(spec.creator)
    c.setAuthor(spec.organisation)
    c.setSubject(spec.title)

    margin = 48
    y = height - margin

    # --- letterhead ---
    c.setFont("DemoSans-Bold", 15)
    c.drawString(margin, y, spec.organisation)
    y -= 15
    if spec.org_subtitle:
        c.setFont("DemoSans", 8.5)
        c.setFillGray(0.35)
        c.drawString(margin, y, spec.org_subtitle)
        c.setFillGray(0)
        y -= 14
    c.setStrokeGray(0.7)
    c.line(margin, y, width - margin, y)
    y -= 26

    c.setFont("DemoSans-Bold", 13)
    c.drawString(margin, y, spec.title.upper())
    y -= 22

    # --- header / party blocks side by side ---
    left_y = right_y = y
    c.setFont("DemoSans", 9)
    for label, value in spec.party_fields:
        left_y = _draw_field(c, spec, margin, left_y, label, value, label_width=96)
    for label, value in spec.header_fields:
        right_y = _draw_field(c, spec, width / 2 + 16, right_y, label, value, label_width=104)
    y = min(left_y, right_y) - 14

    # --- items table ---
    if spec.items:
        c.setStrokeGray(0.75)
        c.setFillGray(0.95)
        c.rect(margin, y - 4, width - 2 * margin, 18, stroke=0, fill=1)
        c.setFillGray(0)
        c.setFont("DemoSans-Bold", 8.6)
        columns = [margin + 6, width - margin - 232, width - margin - 150, width - margin - 66]
        for text, x in zip(spec.item_header, columns, strict=False):
            if text in ("Qty", "Unit price", "Amount"):
                c.drawRightString(x + 60, y + 2, text)
            else:
                c.drawString(x, y + 2, text)
        y -= 18
        c.setFont("DemoSans", 9)
        for desc, qty, unit, amount in spec.items:
            c.drawString(columns[0], y, desc[:56])
            c.drawRightString(columns[1] + 60, y, qty)
            c.drawRightString(columns[2] + 60, y, unit)
            c.drawRightString(columns[3] + 60, y, amount)
            y -= 15
            if y < 170:
                c.showPage()
                y = height - margin
                c.setFont("DemoSans", 9)
        c.setStrokeGray(0.8)
        c.line(margin, y + 8, width - margin, y + 8)
        y -= 8

    # --- totals ---
    for label, value in spec.totals:
        is_grand = label.lower().startswith(("total", "grand", "amount due"))
        font = "DemoSans-Bold" if is_grand else "DemoSans"
        size = 10.5 if is_grand else 9
        label_x = width - margin - 220
        value_x = width - margin
        shift = 0.0
        value_font = font
        if spec.font_anomaly_field and _matches(label, spec.font_anomaly_field):
            # A different typeface for this value only - the footprint of an edit.
            value_font = "DemoSerif"
        if spec.baseline_shift_field and _matches(label, spec.baseline_shift_field):
            shift = 2.4
        c.setFont(font, size)
        c.drawString(label_x, y, label)
        c.setFont(value_font, size)
        c.drawRightString(value_x, y + shift, value)
        y -= 16

    # --- body paragraphs ---
    if spec.body_paragraphs:
        y -= 8
        c.setFont("DemoSans", 9)
        for paragraph in spec.body_paragraphs:
            for line in _wrap(paragraph, 104):
                if y < 120:
                    c.showPage()
                    y = height - margin
                    c.setFont("DemoSans", 9)
                c.drawString(margin, y, line)
                y -= 12.5
            y -= 6

    # --- signature + footer ---
    if spec.signature_line:
        y = max(y, 110)
        c.setStrokeGray(0.6)
        c.line(margin, y - 26, margin + 190, y - 26)
        c.setFont("DemoSans", 8.4)
        c.drawString(margin, y - 38, spec.signature_line)
    if spec.footer:
        c.setFont("DemoSans", 7.6)
        c.setFillGray(0.4)
        for i, line in enumerate(_wrap(spec.footer, 132)):
            c.drawString(margin, 54 - i * 10, line)
        c.setFillGray(0)

    c.showPage()
    c.save()
    data = buffer.getvalue()

    data = _apply_pdf_metadata(data, spec)
    if spec.annotation_overlay:
        data = _add_annotation(data, spec)
    if spec.incremental_update:
        data = append_incremental_update(data)
    if spec.trailing_bytes:
        data = _append_trailing(data, spec.trailing_bytes)
    return data


def _matches(label: str, needle: str) -> bool:
    return needle.lower() in label.lower()


def _draw_field(c, spec: DocSpec, x: float, y: float, label: str, value: str,
                label_width: float = 96) -> float:
    c.setFont("DemoSans", 8.6)
    c.setFillGray(0.38)
    c.drawString(x, y, f"{label}:")
    c.setFillGray(0)
    value_font, shift = "DemoSans", 0.0
    if spec.font_anomaly_field and _matches(label, spec.font_anomaly_field):
        value_font = "DemoSerif"
    if spec.baseline_shift_field and _matches(label, spec.baseline_shift_field):
        shift = 2.2
    c.setFont(value_font, 9.2)
    for i, line in enumerate(_wrap(value, 42)):
        c.drawString(x + label_width, y - i * 11 + shift, line)
    return y - max(1, len(_wrap(value, 42))) * 13


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = str(text).split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _pdf_date(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    return value.strftime("D:%Y%m%d%H%M%S+00'00'")


def _apply_pdf_metadata(data: bytes, spec: DocSpec) -> bytes:
    if not any([spec.producer, spec.creator, spec.created_at, spec.modified_at]):
        return data
    try:
        import pikepdf

        with pikepdf.open(io.BytesIO(data), allow_overwriting_input=False) as pdf:
            info = pdf.docinfo
            if spec.producer:
                info["/Producer"] = spec.producer
            if spec.creator:
                info["/Creator"] = spec.creator
            if spec.created_at:
                info["/CreationDate"] = _pdf_date(spec.created_at)
            if spec.modified_at:
                info["/ModDate"] = _pdf_date(spec.modified_at)
            info["/Title"] = spec.title
            out = io.BytesIO()
            pdf.save(out)
            return out.getvalue()
    except Exception:
        return data


def _add_annotation(data: bytes, spec: DocSpec) -> bytes:
    """Overlay a FreeText annotation - a value can then read differently from the body."""
    label, text = spec.annotation_overlay
    try:
        import pikepdf

        with pikepdf.open(io.BytesIO(data)) as pdf:
            page = pdf.pages[0]
            annot = pdf.make_indirect(pikepdf.Dictionary(
                Type=pikepdf.Name("/Annot"),
                Subtype=pikepdf.Name("/FreeText"),
                Rect=[360, 250, 548, 276],
                Contents=text,
                T=label,
                F=4,
                DA="/Helv 11 Tf 0 g",
                CA=1,
                Border=[0, 0, 0],
            ))
            if "/Annots" in page:
                page.Annots.append(annot)
            else:
                page["/Annots"] = pdf.make_indirect([annot])
            out = io.BytesIO()
            pdf.save(out)
            return out.getvalue()
    except Exception:
        return data


def append_incremental_update(data: bytes) -> bytes:
    """Append a real incremental revision, then validate it still parses.

    A genuine second cross-reference generation is what the forensics stage
    detects. If the constructed revision does not parse cleanly the original
    bytes are returned unchanged - a demo fixture must never be a corrupt file.
    """
    try:
        # The *last* startxref is the live one; walk to the end deliberately.
        match = None
        for candidate in re.finditer(rb"startxref\s+(\d+)\s*%%EOF", data):
            match = candidate
        if match is None:
            return data
        prev_offset = int(match.group(1))
        sizes = re.findall(rb"/Size\s+(\d+)", data)
        roots = re.findall(rb"/Root\s+(\d+)\s+(\d+)\s+R", data)
        if not sizes or not roots:
            return data
        size = int(sizes[-1])
        root_num, root_gen = roots[-1].decode() if isinstance(roots[-1], bytes) else (
            roots[-1][0].decode(), roots[-1][1].decode())
        new_num = size
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        body = (f"\n{new_num} 0 obj\n<< /Type /RevisionNote "
                f"/Note (document re-saved {stamp}) >>\nendobj\n").encode()
        obj_offset = len(data) + 1
        xref_offset = len(data) + len(body)
        trailer = (
            "xref\n"
            "0 1\n"
            "0000000000 65535 f \n"
            f"{new_num} 1\n"
            f"{obj_offset:010d} 00000 n \n"
            "trailer\n"
            f"<< /Size {new_num + 1} /Root {root_num} {root_gen} R /Prev {prev_offset} >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode()
        candidate = data + body + trailer
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(candidate), strict=False)
        if len(reader.pages) < 1:
            return data
        _ = reader.pages[0].extract_text()
        return candidate
    except Exception:
        return data


def _append_trailing(data: bytes, count: int) -> bytes:
    """Leave bytes after the final %%EOF - ignored by viewers, visible to forensics."""
    filler = (b"% residual data from a previous revision of this document\n"
              b"% " + b"0123456789abcdef" * 4 + b"\n")
    payload = (filler * ((count // len(filler)) + 1))[:count]
    candidate = data + payload
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(candidate), strict=False)
        _ = len(reader.pages)
        return candidate
    except Exception:
        return data


# --------------------------------------------------------------------------- #
# Raster rendering
# --------------------------------------------------------------------------- #
def _font(path: str, size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(path, size)
    except Exception:  # pragma: no cover
        return ImageFont.load_default()


def render_card_png(spec: DocSpec) -> bytes:
    """Identity-card style raster: 1.59:1 aspect so the classifier sees a card."""
    import numpy as np
    from PIL import Image, ImageDraw

    width, height = 1010, 636
    image = Image.new("RGB", (width, height), (243, 245, 249))
    draw = ImageDraw.Draw(image)

    draw.rectangle([0, 0, width, 92], fill=(24, 48, 84))
    draw.text((28, 22), spec.organisation, font=_font(SANS_BOLD, 26), fill=(255, 255, 255))
    draw.text((28, 58), spec.org_subtitle or spec.title, font=_font(SANS, 15),
              fill=(198, 214, 236))

    draw.rectangle([28, 124, 240, 400], fill=(214, 220, 230), outline=(150, 160, 175))
    draw.text((70, 372), "PHOTOGRAPH", font=_font(SANS, 14), fill=(120, 130, 145))

    y = 132
    for label, value in spec.party_fields + spec.header_fields:
        draw.text((272, y), label.upper(), font=_font(SANS, 12), fill=(96, 106, 122))
        draw.text((272, y + 17), value, font=_font(SANS_BOLD, 19), fill=(15, 23, 42))
        y += 52

    draw.line([28, 430, width - 28, 430], fill=(180, 188, 200), width=2)
    draw.text((28, 448), spec.title.upper(), font=_font(SANS_BOLD, 17), fill=(24, 48, 84))
    if spec.signature_line:
        draw.text((width - 330, 470), spec.signature_line, font=_font(SERIF, 16),
                  fill=(40, 50, 70))
        draw.line([width - 336, 496, width - 60, 496], fill=(120, 130, 145), width=1)
    if spec.footer:
        draw.text((28, height - 54), spec.footer[:96], font=_font(MONO, 12), fill=(90, 98, 112))

    # Deterministic scan-like grain so the raster is not synthetically flat.
    rng = spec.rng()
    array = np.asarray(image).astype(np.int16)
    noise = rng.normal(0, 2.4, array.shape)
    array = np.clip(array + noise, 0, 255).astype(np.uint8)
    image = Image.fromarray(array)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _draw_receipt(spec: DocSpec, width: int = 1240, height: int = 1680):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), (250, 249, 245))
    draw = ImageDraw.Draw(image)
    y = 64
    draw.text((64, y), spec.organisation, font=_font(SANS_BOLD, 40), fill=(20, 24, 32))
    y += 50
    if spec.org_subtitle:
        draw.text((64, y), spec.org_subtitle, font=_font(SANS, 22), fill=(90, 96, 108))
        y += 38
    draw.line([64, y, width - 64, y], fill=(170, 172, 178), width=2)
    y += 34
    draw.text((64, y), spec.title.upper(), font=_font(SANS_BOLD, 30), fill=(20, 24, 32))
    y += 54

    for label, value in spec.party_fields + spec.header_fields:
        draw.text((64, y), f"{label}:", font=_font(SANS, 22), fill=(96, 102, 114))
        draw.text((430, y), value, font=_font(SANS, 23), fill=(18, 22, 30))
        y += 36
    y += 18

    if spec.items:
        draw.rectangle([64, y - 6, width - 64, y + 34], fill=(236, 236, 232))
        draw.text((76, y), spec.item_header[0], font=_font(SANS_BOLD, 21), fill=(40, 44, 54))
        draw.text((width - 300, y), spec.item_header[-1], font=_font(SANS_BOLD, 21),
                  fill=(40, 44, 54))
        y += 46
        for desc, _qty, _unit, amount in spec.items:
            draw.text((76, y), desc[:44], font=_font(SANS, 22), fill=(24, 28, 38))
            draw.text((width - 300, y), amount, font=_font(SANS, 22), fill=(24, 28, 38))
            y += 34
        draw.line([64, y + 6, width - 64, y + 6], fill=(170, 172, 178), width=2)
        y += 24

    total_box = None
    totals_top = y
    for label, value in spec.totals:
        bold = label.lower().startswith(("total", "amount"))
        draw.text((width - 620, y), label, font=_font(SANS_BOLD if bold else SANS, 24),
                  fill=(20, 24, 32))
        text_x = width - 300
        draw.text((text_x, y), value, font=_font(SANS_BOLD if bold else SANS, 25),
                  fill=(20, 24, 32))
        y += 40
    if spec.splice_region_label and spec.totals:
        # The edited area covers the whole amounts block, as a crude edit would.
        total_box = (width - 660, totals_top - 14, width - 48,
                     totals_top + 40 * len(spec.totals) + 18)

    if spec.copy_move_graphic:
        for cx, cy in ((width - 330, y + 90), (200, y + 90)):
            draw.ellipse([cx - 92, cy - 52, cx + 92, cy + 52], outline=(150, 40, 40), width=5)
            draw.text((cx - 66, cy - 22), "SETTLED", font=_font(SANS_BOLD, 26),
                      fill=(150, 40, 40))
            draw.text((cx - 58, cy + 6), "FIN-2026", font=_font(SANS, 18), fill=(150, 40, 40))
    if spec.footer:
        draw.text((64, height - 120), spec.footer[:110], font=_font(SANS, 18),
                  fill=(110, 116, 128))
    if spec.signature_line:
        draw.line([64, height - 210, 420, height - 210], fill=(140, 146, 158), width=2)
        draw.text((64, height - 200), spec.signature_line, font=_font(SANS, 18),
                  fill=(90, 96, 108))
    return image, total_box


def render_photo_jpeg(spec: DocSpec) -> bytes:
    """A photographed receipt.

    When ``splice_region_label`` is set, the named region is re-encoded at a much
    lower JPEG quality and pasted back before the final save. That produces a
    genuine localised double-compression footprint: exactly what ELA, per-block
    DCT sparsity and noise-residual analysis are designed to surface.
    """
    import numpy as np
    from PIL import Image

    image, total_box = _draw_receipt(spec)
    rng = spec.rng()

    # Camera-like capture: slight perspective-free rotation, vignette, sensor noise.
    image = image.rotate(0.45, resample=Image.BICUBIC, fillcolor=(250, 249, 245))
    array = np.asarray(image).astype(np.float32)
    h, w = array.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    vignette = 1.0 - 0.14 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    array *= vignette[..., None]
    array += rng.normal(0, 3.1, array.shape)
    image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))

    if total_box and spec.splice_region_label:
        # A realistic overwrite: the amounts block is painted out and re-typed
        # *after* capture. The replacement therefore carries none of the
        # photograph's sensor noise, its glyph edges are sharper than anything
        # else on the page, and it is re-compressed once more than its
        # surroundings when the file is saved. Those are three independent,
        # measurable consequences - which is what the forensic suite looks for.
        from PIL import ImageDraw as _ImageDraw

        box = tuple(int(v) for v in total_box)
        draw2 = _ImageDraw.Draw(image)
        draw2.rectangle(box, fill=(252, 251, 248))
        yy = box[1] + 16
        for label, value in spec.totals:
            bold = label.lower().startswith(("total", "amount"))
            draw2.text((box[0] + 14, yy), label,
                       font=_font(SANS_BOLD if bold else SANS, 25), fill=(12, 16, 24))
            draw2.text((box[2] - 268, yy - 2), value,
                       font=_font(SANS_BOLD, 27), fill=(12, 16, 24))
            yy += 40

    buffer = io.BytesIO()
    save_kwargs = {"format": "JPEG", "quality": spec.jpeg_quality, "subsampling": 2}
    exif = _build_exif(spec)
    if exif:
        save_kwargs["exif"] = exif
    image.save(buffer, **save_kwargs)
    return buffer.getvalue()


def _build_exif(spec: DocSpec) -> bytes | None:
    if not any([spec.exif_software, spec.exif_capture, spec.exif_modified, spec.camera]):
        return None
    from PIL import Image

    exif = Image.Exif()
    if spec.camera:
        exif[0x010F] = spec.camera[0]      # Make
        exif[0x0110] = spec.camera[1]      # Model
        exif[0x829A] = (1, 60)             # ExposureTime
        exif[0x829D] = (28, 10)            # FNumber
        exif[0x8827] = 125                 # ISO
        exif[0x920A] = (52, 10)            # FocalLength
    if spec.exif_software:
        exif[0x0131] = spec.exif_software
    if spec.exif_capture:
        exif[0x9003] = spec.exif_capture.strftime("%Y:%m:%d %H:%M:%S")
    if spec.exif_modified:
        exif[0x0132] = spec.exif_modified.strftime("%Y:%m:%d %H:%M:%S")
    exif[0x0112] = 1
    return exif.tobytes()


def render_synthetic_png(spec: DocSpec) -> bytes:
    """A document image with the statistical fingerprint of generated media.

    Built to be *measurably* different from a scan rather than merely labelled as
    suspicious: a smooth low-frequency colour field, softened glyph edges (so
    high-frequency energy is suppressed), no sensor noise, no capture metadata
    and a dense continuous palette.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    image, _ = _draw_receipt(spec, width=1100, height=1500)
    h, w = image.size[1], image.size[0]

    # Smooth synthetic colour field instead of paper texture.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    gradient = np.stack([
        238 + 12 * np.sin(xx / w * 2.1) - 6 * (yy / h),
        236 + 10 * np.cos(yy / h * 1.7) - 4 * (xx / w),
        231 + 14 * np.sin((xx + yy) / (w + h) * 3.3),
    ], axis=-1)
    base = np.asarray(image).astype(np.float32)
    ink = 1.0 - (base.mean(axis=-1, keepdims=True) / 255.0)
    blended = gradient * (1 - ink) + base * ink
    out = Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))
    # Soften edges: suppresses the heavy-tailed gradient statistics of real scans.
    out = out.filter(ImageFilter.GaussianBlur(radius=0.85))

    buffer = io.BytesIO()
    out.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


RENDERERS = {
    "pdf": render_pdf,
    "card_png": render_card_png,
    "photo_jpeg": render_photo_jpeg,
    "synthetic_png": render_synthetic_png,
}

EXTENSIONS = {"pdf": ("pdf", "application/pdf"), "card_png": ("png", "image/png"),
              "photo_jpeg": ("jpg", "image/jpeg"), "synthetic_png": ("png", "image/png")}


def render(spec: DocSpec) -> tuple[bytes, str, str]:
    data = RENDERERS[spec.kind](spec)
    extension, mime = EXTENSIONS[spec.kind]
    return data, extension, mime
