"""EXIF / image metadata forensics."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from app.db.enums import FindingCategory, Severity
from app.services.forensics.base import MetadataEntry, RawFinding

DETECTOR = "image-metadata-forensics"
DETECTOR_VERSION = "1.2.0"

EDITOR_MARKERS = [
    ("adobe photoshop", "Adobe Photoshop"), ("gimp", "GIMP"), ("paint.net", "Paint.NET"),
    ("pixelmator", "Pixelmator"), ("snapseed", "Snapseed"), ("lightroom", "Adobe Lightroom"),
    ("canva", "Canva"), ("picsart", "PicsArt"), ("photo editor", "a mobile photo editor"),
    ("remini", "Remini"), ("facetune", "Facetune"),
]
CAMERA_KEYS = ("Make", "Model", "LensModel", "ExposureTime", "FNumber", "ISOSpeedRatings",
               "FocalLength", "DateTimeOriginal")


def analyze_image_metadata(
    data: bytes, *, declared_mime: str
) -> tuple[list[MetadataEntry], list[RawFinding], dict]:
    from PIL import ExifTags, Image

    metadata: list[MetadataEntry] = []
    findings: list[RawFinding] = []
    summary: dict = {}

    exif: dict = {}
    info: dict = {}
    try:
        with Image.open(io.BytesIO(data)) as img:
            summary["format"] = img.format
            summary["mode"] = img.mode
            summary["size"] = [img.width, img.height]
            summary["dpi"] = list(img.info.get("dpi", ())) or None
            info = {k: v for k, v in img.info.items() if isinstance(v, (str, int, float, bytes))}
            raw_exif = img.getexif()
            if raw_exif:
                for tag_id, value in raw_exif.items():
                    name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    exif[name] = value
                try:
                    for tag_id, value in raw_exif.get_ifd(0x8769).items():
                        name = ExifTags.TAGS.get(tag_id, str(tag_id))
                        exif[name] = value
                except Exception:
                    pass
    except Exception as exc:
        summary["error"] = type(exc).__name__

    for key, value in exif.items():
        rendered = str(value)
        if len(rendered) > 300:
            rendered = rendered[:300] + "..."
        metadata.append(MetadataEntry("exif", str(key)[:120], rendered))
    for key, value in info.items():
        if key in {"exif", "icc_profile", "photoshop"}:
            metadata.append(MetadataEntry("image_info", key, f"<{len(value)} bytes>"))
            continue
        metadata.append(MetadataEntry("image_info", str(key)[:120], str(value)[:300]))
    for key, value in summary.items():
        metadata.append(MetadataEntry("file", key, str(value)))

    software = str(exif.get("Software", "") or "")
    summary["software"] = software or None
    summary["has_exif"] = bool(exif)
    summary["camera_fields_present"] = [k for k in CAMERA_KEYS if k in exif]

    for needle, label in EDITOR_MARKERS:
        if needle in software.lower():
            findings.append(RawFinding(
                code="IMG_EDITOR_SOFTWARE_TAG", category=FindingCategory.METADATA,
                severity=Severity.HIGH,
                title=f"Image metadata names an editing application: {label}",
                description=(f"The EXIF Software field records {label}. The image was therefore "
                             "opened and re-saved by an editor at some point. That alone does not "
                             "establish that content was altered - resizing or cropping produces "
                             "the same tag - but it should be resolved with the claimant."),
                confidence=0.8, detector=DETECTOR, model_version=DETECTOR_VERSION, page=1,
                evidence={"software": software, "exif_keys": sorted(exif.keys())[:40]},
                recommendation="Request the unedited original capture from the claimant.",
                extras={"signal_group": "metadata"},
            ))
            _mark(metadata, "Software", f"Editing application: {label}")
            break

    if exif:
        original = _exif_datetime(exif.get("DateTimeOriginal"))
        modified = _exif_datetime(exif.get("DateTime"))
        summary["datetime_original"] = original.isoformat() if original else None
        summary["datetime_modified"] = modified.isoformat() if modified else None
        if original and modified and (modified - original).total_seconds() > 3600:
            hours = (modified - original).total_seconds() / 3600.0
            findings.append(RawFinding(
                code="IMG_EXIF_TIMESTAMP_DRIFT", category=FindingCategory.METADATA,
                severity=Severity.MEDIUM,
                title=f"Image re-saved {hours:.1f} hours after capture",
                description=("EXIF records a file modification time well after the capture time, "
                             "meaning the image was written again after it was taken."),
                confidence=0.62, detector=DETECTOR, model_version=DETECTOR_VERSION, page=1,
                evidence={"datetime_original": original.isoformat(),
                          "datetime_modified": modified.isoformat(),
                          "hours_between": round(hours, 2)},
                extras={"signal_group": "metadata"},
            ))
            _mark(metadata, "DateTime", f"{hours:.1f}h after DateTimeOriginal")
        for name, value in (("DateTimeOriginal", original), ("DateTime", modified)):
            if value and value.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                findings.append(RawFinding(
                    code="IMG_EXIF_FUTURE_TIMESTAMP", category=FindingCategory.METADATA,
                    severity=Severity.MEDIUM,
                    title=f"EXIF {name} is in the future",
                    description="A capture timestamp later than now indicates a manipulated or "
                                "misconfigured clock.",
                    confidence=0.65, detector=DETECTOR, model_version=DETECTOR_VERSION, page=1,
                    evidence={name: value.isoformat()}, extras={"signal_group": "metadata"},
                ))
                _mark(metadata, name, "Timestamp in the future")
    elif declared_mime in {"image/jpeg", "image/tiff"}:
        findings.append(RawFinding(
            code="IMG_EXIF_STRIPPED", category=FindingCategory.METADATA,
            severity=Severity.LOW,
            title="No EXIF metadata present on a photographic format",
            description=("JPEG/TIFF captures normally carry camera EXIF. Its absence is expected "
                         "for screenshots, exports and images passed through messaging apps, and "
                         "is also the result of deliberately stripping provenance."),
            confidence=0.45, detector=DETECTOR, model_version=DETECTOR_VERSION, page=1,
            evidence={"has_exif": False, "declared_mime": declared_mime},
            extras={"signal_group": "metadata"},
        ))
    return metadata, findings, summary


def _exif_datetime(value) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


def _mark(metadata: list[MetadataEntry], key: str, note: str) -> None:
    for entry in metadata:
        if entry.key.lower() == key.lower():
            entry.is_anomalous = True
            entry.note = note
