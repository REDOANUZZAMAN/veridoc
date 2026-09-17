"""Analysis pipeline orchestrator.

Implements the product workflow end to end:

    security check -> render -> OCR -> classification -> field extraction ->
    metadata analysis -> image/PDF forensics -> AIGC analysis ->
    tampering correlation -> consistency rules -> cross-document comparison ->
    trusted-source verification -> risk assessment

Two invariants govern the implementation:

1. **The original is never lost.** Stages read the stored original; nothing
   mutates or deletes it. A stage failure degrades that stage only.
2. **Human decisions survive reprocessing.** Confirmed/dismissed findings are
   snapshotted before regeneration and re-applied to the equivalent new finding.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PIPELINE_VERSION, RULES_VERSION, settings
from app.core.errors import AppError, ProviderUnavailable
from app.core.logging import get_logger
from app.db.enums import (
    DOCUMENT_TYPE_LABELS,
    AuditAction,
    ClaimStatus,
    DocumentType,
    FindingCategory,
    InvestigationStatus,
    MalwareStatus,
    ProcessingStatus,
    RiskBand,
    Severity,
    StageStatus,
    VerificationOutcome,
    VerificationState,
)
from app.db.models.analysis import AnalysisRun, RiskAssessment
from app.db.models.claim import Claim
from app.db.models.config import DetectionRule, SystemSetting
from app.db.models.document import (
    Document,
    DocumentMetadataEntry,
    DocumentPage,
    ExtractedField,
    OcrResult,
)
from app.db.models.investigation import Investigation
from app.db.models.user import User
from app.db.models.verification import VerificationRequest, VerificationResult
from app.services import audit, findings_store
from app.services.aigc.base import AigcTarget
from app.services.aigc.factory import get_aigc_provider
from app.services.classify.classifier import classify
from app.services.consistency.engine import run_consistency
from app.services.crossdoc.engine import DocumentSnapshot, compare_documents
from app.services.extract.engine import extract_fields
from app.services.extract.schema import schema_for
from app.services.forensics import image as image_forensics
from app.services.forensics import image_meta, text_layout
from app.services.forensics.base import RawFinding
from app.services.forensics.pdf import analyze_pdf
from app.services.forensics.pdf_images import extract_embedded_rasters
from app.services.malware.scanner import get_scanner
from app.services.ocr.base import OcrPageResult, OcrTarget
from app.services.ocr.factory import get_ocr_provider
from app.services.render import render_document
from app.services.risk import engine as risk_engine
from app.services.storage.factory import get_storage
from app.services.tampering.detector import detect_tampering
from app.services.verification.base import VerificationQuery
from app.services.verification.factory import (
    PLAN_BY_DOCUMENT_TYPE,
    REQUEST_PAYLOAD_FIELDS,
    get_verification_provider,
)

logger = get_logger(__name__)

PIXEL_ANALYSIS_PAGE_LIMIT = 12
OCR_PAGE_LIMIT = 30

STAGE_DEFINITIONS: list[tuple[str, str, bool]] = [
    # (key, label, critical)
    ("validation", "File validation", True),
    ("security_scan", "Malware / security check", True),
    ("render", "Page rendering", True),
    ("ocr", "OCR & text extraction", True),
    ("classification", "Document classification", True),
    ("extraction", "Field extraction", True),
    ("metadata", "Metadata analysis", False),
    ("forensics", "Image & PDF forensics", False),
    ("aigc", "AI-generated content analysis", False),
    ("tampering", "Tampering detection", False),
    ("consistency", "Document consistency", False),
    ("cross_document", "Cross-document comparison", False),
    ("verification", "Trusted-source verification", False),
    ("risk", "Fraud risk assessment", True),
]

VERIFICATION_PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "policy_lookup": ("policy_number",),
    "provider_lookup": ("hospital_name", "garage_name"),
    "invoice_lookup": ("invoice_number",),
    "identity_lookup": ("national_id",),
    "vehicle_lookup": ("vehicle_registration", "vin"),
    "payment_lookup": ("transaction_reference",),
}


@dataclass
class StageRecord:
    key: str
    label: str
    status: str = StageStatus.PENDING
    message: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int = 0
    findings: int = 0
    provider: dict | None = None
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "status": self.status,
            "message": self.message, "started_at": self.started_at,
            "finished_at": self.finished_at, "duration_ms": self.duration_ms,
            "findings": self.findings, "provider": self.provider, "detail": self.detail,
        }


class AnalysisPipeline:
    def __init__(self, db: Session, document: Document, run: AnalysisRun, actor: User | None = None):
        self.db = db
        self.doc = document
        self.run = run
        self.actor = actor
        self.storage = get_storage()
        self.stages: dict[str, StageRecord] = {
            key: StageRecord(key=key, label=label) for key, label, _ in STAGE_DEFINITIONS
        }
        self.critical = {key for key, _, crit in STAGE_DEFINITIONS if crit}
        self.raw_findings: list[RawFinding] = []
        self.state: dict[str, Any] = {}

    # ------------------------------------------------------------------ helpers
    @contextmanager
    def stage(self, key: str):
        record = self.stages[key]
        record.status = StageStatus.RUNNING
        record.started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        self._flush_stages()
        try:
            yield record
            if record.status == StageStatus.RUNNING:
                record.status = StageStatus.COMPLETED
        except ProviderUnavailable as exc:
            record.status = StageStatus.UNAVAILABLE
            record.message = exc.message
            logger.warning("stage_provider_unavailable",
                           extra={"stage": key, "document": self.doc.document_ref})
        except AppError as exc:
            record.status = StageStatus.FAILED
            record.message = exc.message
            logger.warning("stage_failed", extra={"stage": key, "code": exc.code})
        except Exception as exc:  # pragma: no cover - defensive
            record.status = StageStatus.FAILED
            record.message = f"Unexpected {type(exc).__name__}: {str(exc)[:200]}"
            logger.exception("stage_crashed", extra={"stage": key})
        finally:
            record.duration_ms = int((time.perf_counter() - started) * 1000)
            record.finished_at = datetime.now(timezone.utc).isoformat()
            self._flush_stages()

    def _flush_stages(self) -> None:
        self.run.stages = [self.stages[key].as_dict() for key, _, _ in STAGE_DEFINITIONS]
        self.db.flush()

    def _add(self, findings: list[RawFinding], record: StageRecord) -> None:
        self.raw_findings.extend(findings)
        record.findings += len(findings)

    @property
    def is_pdf(self) -> bool:
        return self.doc.mime_type == "application/pdf"

    # --------------------------------------------------------------------- main
    def execute(self) -> AnalysisRun:
        self.run.status = ProcessingStatus.PROCESSING
        self.run.started_at = datetime.now(timezone.utc)
        self.doc.processing_status = ProcessingStatus.PROCESSING
        self.doc.processing_message = None
        self.db.flush()

        review_state = findings_store.snapshot_review_state(self.db, self.doc.id)
        findings_store.clear_findings(self.db, self.doc.id)

        self._stage_validation()
        blocked = self._stage_security()
        if not blocked:
            self._stage_render()
            self._stage_ocr()
            self._stage_classification()
            self._stage_extraction()
            self._stage_metadata()
            self._stage_forensics()
            self._stage_aigc()
            self._stage_tampering()
            self._stage_consistency()

        persisted = findings_store.persist(
            self.db, [f for f in self.raw_findings
                      if f.category != FindingCategory.CROSS_DOCUMENT],
            document_id=self.doc.id, claim_id=self.doc.claim_id,
            analysis_run_id=self.run.id, review_state=review_state,
        )

        if not blocked:
            self._stage_cross_document(review_state)
            self._stage_verification()
        self._stage_risk()

        self._finalise(len(persisted))
        return self.run

    # ------------------------------------------------------------------- stages
    def _stage_validation(self) -> None:
        with self.stage("validation") as record:
            record.detail = {
                "sha256": self.doc.sha256,
                "file_size": self.doc.file_size,
                "mime_type": self.doc.mime_type,
                "declared_mime_type": self.doc.declared_mime_type,
                "page_count": self.doc.page_count,
                "original_filename": self.doc.original_filename,
            }
            data = self.storage.read("originals", self.doc.storage_key)
            self.state["original_bytes"] = data
            from app.core.security import sha256_bytes

            digest = sha256_bytes(data)
            record.detail["integrity_hash_recomputed"] = digest
            record.detail["integrity_verified"] = digest == self.doc.sha256
            if digest != self.doc.sha256:
                record.status = StageStatus.FAILED
                record.message = (
                    "Stored bytes no longer match the SHA-256 recorded at upload. The document "
                    "has not been modified by this platform - investigate the storage layer."
                )
                return
            record.message = (f"Integrity confirmed against the upload hash "
                              f"({self.doc.page_count} page(s), "
                              f"{self.doc.file_size / 1024:.0f} KB).")

            duplicates = self.db.execute(
                select(Document).where(
                    Document.sha256 == self.doc.sha256,
                    Document.id != self.doc.id,
                    Document.deleted_at.is_(None),
                )
            ).scalars().all()
            if duplicates:
                others = ", ".join(
                    d.document_ref + (f" (claim {d.claim.claim_number})" if d.claim else "")
                    for d in duplicates[:5]
                )
                record.detail["duplicate_of"] = [d.document_ref for d in duplicates]
                cross_claim = any(d.claim_id != self.doc.claim_id for d in duplicates)
                # Only the *later* submission is the anomaly. The document that
                # was filed first is not suspect merely because someone re-used
                # it afterwards, so it records the link at informational level.
                is_earliest = all(
                    (d.uploaded_at or self.doc.uploaded_at) >= self.doc.uploaded_at
                    for d in duplicates
                )
                if is_earliest:
                    severity, confidence = Severity.INFO, 0.9
                    description = (
                        f"The SHA-256 of this document also appears on {others}, submitted later. "
                        "This document was filed first, so the duplication is recorded here for "
                        "traceability only - the later submission carries the duplicate-billing "
                        "signal."
                    )
                    title = f"This file was re-submitted later as {len(duplicates)} document(s)"
                else:
                    severity = Severity.HIGH if cross_claim else Severity.MEDIUM
                    confidence = 0.95
                    title = (f"Byte-identical copy of {len(duplicates)} document(s) already "
                             "on record")
                    description = (
                        f"The SHA-256 of this upload matches {others}. An identical file submitted "
                        "against a different claim is a recognised duplicate-billing pattern; "
                        "within the same claim it is usually a re-upload."
                    )
                self._add([RawFinding(
                    code="DOC_DUPLICATE_CONTENT_HASH", category=FindingCategory.CONSISTENCY,
                    severity=severity, title=title, description=description,
                    confidence=confidence, detector="ingest-integrity", model_version="1.0.0",
                    evidence={"sha256": self.doc.sha256,
                              "duplicates": [
                                  {"document_ref": d.document_ref, "claim_id": d.claim_id,
                                   "uploaded_at": d.uploaded_at.isoformat()}
                                  for d in duplicates[:5]],
                              "cross_claim": cross_claim,
                              "this_document_filed_first": is_earliest},
                    recommendation=(None if is_earliest else
                                    "Check whether the same expense is being claimed twice."),
                    extras={"rule_code": "DOC_DUPLICATE_CONTENT_HASH",
                            "fields_involved": ["sha256"]},
                )], record)

    def _stage_security(self) -> bool:
        """Returns True when the pipeline must stop (quarantine)."""
        blocked = False
        with self.stage("security_scan") as record:
            data = self.state.get("original_bytes")
            if data is None:
                raise ProviderUnavailable("storage", "Original bytes unavailable for scanning.")
            scanner = get_scanner()
            record.provider = {"key": scanner.key, "label": scanner.label,
                               "version": scanner.version}
            result = scanner.scan(data, self.doc.original_filename, self.doc.mime_type)
            self.doc.malware_status = result.status
            self.doc.malware_detail = result.as_dict()
            record.message = result.message
            record.detail = result.as_dict()
            if result.status == MalwareStatus.INFECTED:
                self.doc.processing_status = ProcessingStatus.QUARANTINED
                blocked = True
                self._add([RawFinding(
                    code="SEC_MALWARE_SIGNATURE", category=FindingCategory.SECURITY,
                    severity=Severity.CRITICAL,
                    title="Malware signature detected in the uploaded file",
                    description=(f"{scanner.label} matched: "
                                 f"{', '.join(result.signatures) or 'unnamed signature'}. "
                                 "The file has been quarantined. It is retained as evidence and "
                                 "is not processed further."),
                    confidence=0.97, detector=scanner.key, model_version=scanner.version,
                    evidence=result.as_dict(),
                    recommendation="Do not open outside an isolated environment.",
                    extras={"signal_group": "security"},
                )], record)
            elif result.status == MalwareStatus.SUSPICIOUS:
                self._add([RawFinding(
                    code="SEC_ACTIVE_CONTENT", category=FindingCategory.SECURITY,
                    severity=Severity.HIGH,
                    title="Active content indicators in the uploaded file",
                    description=(("Static inspection found active-content constructs: "
                                  + "; ".join(i["detail"] for i in result.indicators[:4]))
                                 + ". Claim documents do not normally contain executable "
                                   "constructs."),
                    confidence=0.72, detector=scanner.key, model_version=scanner.version,
                    evidence=result.as_dict(),
                    recommendation="Request a flattened PDF or a plain image from the claimant.",
                    extras={"signal_group": "security"},
                )], record)
            elif result.status == MalwareStatus.UNAVAILABLE:
                record.status = StageStatus.UNAVAILABLE
        return blocked

    def _stage_render(self) -> None:
        with self.stage("render") as record:
            data = self.state["original_bytes"]
            for page in list(self.doc.pages):
                self.db.delete(page)
            self.db.flush()
            pages = render_document(
                data, self.doc.mime_type, self.doc.artifact_prefix, self.storage
            )
            self.state["rendered"] = pages
            page_rows = []
            for page in pages:
                row = DocumentPage(
                    document_id=self.doc.id, page_number=page.page_number,
                    width=page.width, height=page.height, render_key=page.render_key,
                    render_dpi=page.dpi,
                    artifacts={"thumbnail": page.thumb_key},
                )
                self.db.add(row)
                page_rows.append(row)
            self.db.flush()
            self.state["page_rows"] = {r.page_number: r for r in page_rows}
            self.state["page_sizes"] = {p.page_number: (p.width, p.height) for p in pages}
            if self.doc.page_count != len(pages):
                self.doc.page_count = len(pages)
            record.message = f"Rendered {len(pages)} page(s) at {settings.render_dpi} DPI."
            record.detail = {"pages": len(pages),
                            "dimensions": {p.page_number: [p.width, p.height] for p in pages}}

    def _stage_ocr(self) -> None:
        with self.stage("ocr") as record:
            provider = get_ocr_provider()
            available, detail = provider.available()
            record.provider = {**provider.describe()}
            if not available:
                raise ProviderUnavailable("ocr", detail)
            self.db.execute(
                OcrResult.__table__.delete().where(OcrResult.document_id == self.doc.id)
            )
            results: list[OcrPageResult] = []
            errors: list[str] = []
            pages = self.state.get("rendered", [])[:OCR_PAGE_LIMIT]
            for page in pages:
                target = OcrTarget(
                    page_number=page.page_number, image_bytes=page.png_bytes,
                    width=page.width, height=page.height,
                    pdf_bytes=self.state["original_bytes"] if self.is_pdf else None,
                    dpi=page.dpi, language=settings.ocr_language,
                    artifact_prefix=self.doc.artifact_prefix,
                )
                try:
                    result = provider.extract(target)
                except ProviderUnavailable as exc:
                    errors.append(f"page {page.page_number}: {exc.message}")
                    continue
                results.append(result)
                self.db.add(OcrResult(
                    document_id=self.doc.id, page_number=result.page_number,
                    provider=result.provider, provider_version=result.provider_version,
                    status=result.status, error=result.error, raw_text=result.text,
                    mean_confidence=result.mean_confidence, word_count=result.word_count,
                    words=[w.as_dict() for w in result.words], duration_ms=result.duration_ms,
                ))
                row = self.state["page_rows"].get(result.page_number)
                if row is not None:
                    row.text_char_count = len(result.text)
                    row.has_text_layer = (
                        result.engine_detail.get("route") == "pdf_text_layer"
                    )
            self.db.flush()
            self.state["ocr"] = results
            self.state["page_texts"] = {r.page_number: r.text for r in results}
            if not results:
                raise ProviderUnavailable(
                    "ocr", "No page could be processed. " + ("; ".join(errors) or "Unknown cause.")
                )
            mean_conf = sum(r.mean_confidence or 0 for r in results) / len(results)
            words = sum(r.word_count for r in results)
            record.message = (f"Recognised {words} words across {len(results)} page(s) "
                              f"(mean confidence {mean_conf:.1%}).")
            record.detail = {
                "pages_processed": len(results), "word_count": words,
                "mean_confidence": round(mean_conf, 4),
                "routes": {r.page_number: r.engine_detail.get("route", provider.key)
                           for r in results},
                "errors": errors,
            }
            if words < 8:
                record.message += (" Very little text was recognised - field extraction and "
                                   "consistency checks will have limited coverage.")

    def _stage_classification(self) -> None:
        with self.stage("classification") as record:
            text = "\n".join(self.state.get("page_texts", {}).values())
            sizes = [self.state["page_sizes"][k] for k in sorted(self.state["page_sizes"])]
            result = classify(text, page_count=self.doc.page_count, page_sizes=sizes)
            self.state["classification"] = result
            self.doc.classification_type = result.document_type
            self.doc.classification_confidence = result.confidence
            self.doc.classification_detail = result.as_dict()
            record.provider = {"key": result.method, "version": result.version}
            record.message = (f"{result.label} at {result.confidence:.0%} confidence"
                              + (f" - {result.note}" if result.note else ""))
            record.detail = result.as_dict()
            if result.document_type == DocumentType.OTHER:
                self._add([RawFinding(
                    code="CLS_UNRECOGNISED_DOCUMENT_TYPE", category=FindingCategory.CONSISTENCY,
                    severity=Severity.LOW,
                    title="Document type could not be determined",
                    description=("No document-type signature matched with sufficient evidence, so "
                                 "the generic schema was used. Type-specific consistency rules "
                                 "and verification routes were therefore not applied."),
                    confidence=0.5, detector=result.method, model_version=result.version,
                    evidence=result.as_dict(),
                    recommendation="Set the document type manually if it is known.",
                    extras={"rule_code": "CLS_UNRECOGNISED_DOCUMENT_TYPE",
                            "fields_involved": []},
                )], record)

    def _stage_extraction(self) -> None:
        with self.stage("extraction") as record:
            schema = schema_for(self.doc.classification_type)
            result = extract_fields(self.state.get("ocr", []), schema)
            self.state["extraction"] = result
            self.state["schema"] = schema
            self.db.execute(
                ExtractedField.__table__.delete().where(
                    ExtractedField.document_id == self.doc.id)
            )
            for f in result.fields:
                self.db.add(ExtractedField(
                    document_id=self.doc.id, field_key=f.key, field_label=f.label,
                    value_raw=f.value_raw, value_normalized=f.value_normalized,
                    value_type=f.value_type, confidence=f.confidence, page=f.page,
                    bbox=f.bbox, source=f.source, is_required=f.required, group_name=f.group,
                    line_index=f.line_index,
                ))
            for item in result.line_items:
                self.db.add(ExtractedField(
                    document_id=self.doc.id, field_key=f"line_item_{item.index}",
                    field_label=f"{schema.line_item_label} #{item.index}",
                    value_raw=item.raw,
                    value_normalized=f"{item.description} = {item.amount}",
                    value_type="list", confidence=0.85, page=item.page, bbox=item.bbox,
                    source="ocr", is_required=False, group_name="line_items",
                ))
            self.db.flush()
            record.provider = {"key": result.extractor, "version": result.version}
            record.message = (f"Extracted {len(result.fields)} field(s) and "
                              f"{len(result.line_items)} line item(s) using the "
                              f"{schema.label} schema.")
            record.detail = {**result.stats, "schema": schema.document_type,
                            "missing_required": result.missing_required}

    def _stage_metadata(self) -> None:
        with self.stage("metadata") as record:
            data = self.state["original_bytes"]
            self.db.execute(
                DocumentMetadataEntry.__table__.delete().where(
                    DocumentMetadataEntry.document_id == self.doc.id)
            )
            if self.is_pdf:
                entries, findings, structure = analyze_pdf(data)
                self.state["pdf_structure"] = structure
                record.detail = {"source": "pdf", **{
                    k: v for k, v in structure.items() if k != "pages"}}
            else:
                entries, findings, summary = image_meta.analyze_image_metadata(
                    data, declared_mime=self.doc.mime_type
                )
                self.state["image_metadata"] = summary
                record.detail = {"source": "image", **summary}
            for entry in entries:
                self.db.add(DocumentMetadataEntry(
                    document_id=self.doc.id, group_name=entry.group, key=entry.key,
                    value=entry.value, is_anomalous=entry.is_anomalous, note=entry.note,
                    raw=entry.raw,
                ))
            self.db.flush()
            self._add(findings, record)
            anomalies = sum(1 for e in entries if e.is_anomalous)
            record.message = (f"Catalogued {len(entries)} metadata field(s); "
                              f"{anomalies} flagged as anomalous.")

    def _stage_forensics(self) -> None:
        with self.stage("forensics") as record:
            suspect: list[dict] = []
            features: dict = {}
            pages = self.state.get("rendered", [])[:PIXEL_ANALYSIS_PAGE_LIMIT]

            if self.is_pdf:
                # Pixel-history metrics (ELA, noise residual, compression
                # quality, resampling) only carry information where there is a
                # real capture/compression history. A vector PDF page render has
                # none - measuring it would measure the renderer. So for PDFs the
                # raster suite runs over *embedded* raster objects, which is
                # where a scan or a pasted graphic actually lives.
                rasters, extraction_info = extract_embedded_rasters(
                    self.state["original_bytes"], self.state.get("page_sizes", {}),
                    page_limit=PIXEL_ANALYSIS_PAGE_LIMIT,
                )
                features["embedded_rasters"] = extraction_info
                for raster in rasters:
                    report = image_forensics.analyze_raster(
                        raster.data, page=raster.page, origin="pdf_embedded_image",
                        coord_scale=raster.coord_scale if raster.covers_page else 0.0,
                        is_lossless_render=False,
                    )
                    if not raster.covers_page:
                        # Placement of a partial graphic is not resolvable from the
                        # object alone, so findings are reported without a region.
                        for finding in report.findings:
                            finding.region = None
                            finding.evidence["object_name"] = raster.name
                            finding.evidence["placement"] = "unresolved_partial_graphic"
                        report.suspect_regions = []
                    self._absorb_image_report(report, raster.page, record, suspect, features)
                if not rasters:
                    features["raster"] = {
                        "status": "not_applicable",
                        "reason": ("The page content is vector text and graphics with no embedded "
                                   "raster objects, so compression-history, sensor-noise and "
                                   "resampling metrics do not apply. Structural, metadata, font "
                                   "and typography analysis carry the forensic signal for this "
                                   "document."),
                    }
                layout = text_layout.analyze_pdf_fonts(
                    self.state["original_bytes"], self.state.get("page_sizes", {})
                )
                self._add(layout.findings, record)
                suspect.extend(layout.suspect_regions)
                features["pdf_fonts"] = layout.features
            else:
                original = self.state["original_bytes"]
                first = pages[0] if pages else None
                scale = 1.0
                if first is not None:
                    decoded = image_forensics.decode(original)
                    if decoded is not None and decoded.shape[1]:
                        scale = first.width / float(decoded.shape[1])
                report = image_forensics.analyze_raster(
                    original, page=1, origin="original_upload", coord_scale=scale,
                    is_lossless_render=False,
                )
                self._absorb_image_report(report, 1, record, suspect, features)
                features["coordinate_scale_to_render"] = round(scale, 4)
                for page in pages[1:]:
                    extra = image_forensics.analyze_raster(
                        page.png_bytes, page=page.page_number, origin="frame_render",
                        coord_scale=1.0, is_lossless_render=True,
                    )
                    self._absorb_image_report(extra, page.page_number, record, suspect, features)

            for ocr_page in self.state.get("ocr", []):
                page = next((p for p in pages if p.page_number == ocr_page.page_number), None)
                layout = text_layout.analyze_layout(ocr_page, page.png_bytes if page else None)
                self._add(layout.findings, record)
                suspect.extend(layout.suspect_regions)
                features.setdefault("layout", {})[ocr_page.page_number] = layout.features

            self.state["suspect_regions"] = suspect
            self.state["forensic_features"] = features
            record.detail = features
            raster_note = features.get("raster", {})
            record.message = (
                f"{len(suspect)} candidate region(s) flagged for correlation across "
                f"{len(pages)} page(s)."
                + (" Pixel-history metrics were not applicable (vector page content)."
                   if isinstance(raster_note, dict)
                   and raster_note.get("status") == "not_applicable" else "")
            )

    def _absorb_image_report(self, report, page_number: int, record, suspect: list, features: dict):
        self._add(report.findings, record)
        suspect.extend(report.suspect_regions)
        features.setdefault("raster", {})[page_number] = report.features
        if report.error:
            features.setdefault("raster_errors", {})[page_number] = report.error
        row = self.state.get("page_rows", {}).get(page_number)
        for name, payload in (report.artifacts or {}).items():
            key = f"{self.doc.artifact_prefix}/forensics/page-{page_number:03d}-{name}.png"
            try:
                self.storage.write("artifacts", key, payload, "image/png")
                if row is not None:
                    row.artifacts = {**(row.artifacts or {}), name: key}
            except Exception as exc:  # pragma: no cover
                logger.warning("artifact_write_failed", extra={"detail": str(exc)[:120]})

    def _stage_aigc(self) -> None:
        with self.stage("aigc") as record:
            provider = get_aigc_provider()
            available, detail = provider.available()
            record.provider = provider.describe()
            if not available:
                raise ProviderUnavailable("aigc", detail)

            exif = self.state.get("image_metadata", {}) or {}
            has_camera = bool(exif.get("camera_fields_present"))
            pages = self.state.get("rendered", [])[:PIXEL_ANALYSIS_PAGE_LIMIT]
            results = []
            for page in pages:
                ocr_page = next((o for o in self.state.get("ocr", [])
                                 if o.page_number == page.page_number), None)
                use_original = (not self.is_pdf) and page.page_number == 1
                target = AigcTarget(
                    page_number=page.page_number,
                    image_bytes=(self.state["original_bytes"] if use_original
                                 else page.png_bytes),
                    is_lossless_render=not use_original,
                    source_mime=self.doc.mime_type if use_original else "image/png",
                    has_camera_exif=has_camera,
                    exif_summary=exif,
                    ocr_confidences=[w.confidence for w in (ocr_page.words if ocr_page else [])],
                    glyph_heights=[float(w.bbox.height)
                                   for w in (ocr_page.words if ocr_page else [])],
                    document_type=self.doc.classification_type,
                )
                result = provider.analyze(target)
                results.append(result)
                self._add([self._aigc_finding(result)], record)
            self.state["aigc"] = results
            top = max(results, key=lambda r: r.likelihood) if results else None
            record.message = (
                f"{provider.label} evaluated {len(results)} page(s); highest likelihood "
                f"{top.likelihood:.2f} ({top.band_label.lower()})." if top
                else "No page was available for synthetic-media analysis."
            )
            record.detail = {
                "pages": [r.as_dict() for r in results],
                "is_demo_provider": provider.is_demo,
                "disclaimer": provider.disclaimer,
            }

    def _aigc_finding(self, result) -> RawFinding:
        from app.services.aigc.base import (
            BAND_NONE,
            BAND_NOTABLE,
            BAND_POSSIBLE,
            BAND_WEAK,
            UNCERTAINTY_NOTE,
        )

        raised = result.band != BAND_NONE
        confidence = result.likelihood if raised else max(0.35, 1.0 - result.likelihood)
        # Severity tracks the published band rather than a generic confidence
        # curve, so the finding's weight in triage matches the wording shown to
        # the investigator.
        severity = {
            BAND_NONE: Severity.INFO,
            BAND_WEAK: Severity.LOW,
            BAND_POSSIBLE: Severity.MEDIUM,
            BAND_NOTABLE: Severity.HIGH,
        }.get(result.band, Severity.LOW)
        indicators = {i.key: round(i.normalized, 4) for i in result.indicators}
        return RawFinding(
            code=("AIGC_SYNTHETIC_INDICATORS" if raised else "AIGC_NO_SIGNIFICANT_INDICATORS"),
            category=FindingCategory.AIGC, severity=severity,
            title=f"{result.band_label} (page {result.page_number})",
            description=f"{result.summary} {UNCERTAINTY_NOTE}",
            confidence=confidence, detector=result.provider_key,
            model_version=f"{result.model_name}@{result.model_version}",
            page=result.page_number,
            region=(result.region_hints[0] if result.region_hints else None),
            evidence={**result.evidence, "likelihood": round(result.likelihood, 4),
                      "band": result.band, "indicators": [i.as_dict() for i in result.indicators],
                      "provider_is_demo": result.is_demo,
                      "provider_disclaimer": result.disclaimer},
            recommendation=("Corroborate with metadata provenance and issuer verification."
                            if raised else None),
            extras={
                "provider_key": result.provider_key, "provider_label": result.provider_label,
                "is_demo_provider": result.is_demo, "indicator_scores": indicators,
                "likelihood_band": result.band,
            },
        )

    def _stage_tampering(self) -> None:
        with self.stage("tampering") as record:
            extraction = self.state.get("extraction")
            if extraction is None:
                record.status = StageStatus.SKIPPED
                record.message = "Field extraction did not complete, so regions cannot be named."
                return
            annotation_regions = self._pdf_annotation_regions()
            findings, regions = detect_tampering(
                suspect_regions=self.state.get("suspect_regions", []) + annotation_regions,
                fields=extraction.fields,
                line_items=extraction.line_items,
                page_texts=self.state.get("page_texts", {}),
                page_sizes=self.state.get("page_sizes", {}),
            )
            self._add(findings, record)
            self.state["tamper_regions"] = regions
            record.detail = {"regions": regions,
                            "candidate_regions": len(self.state.get("suspect_regions", []))}
            record.message = (
                f"Correlated {len(self.state.get('suspect_regions', []))} candidate region(s) "
                f"into {len(regions)} region-level tampering signal(s)."
                if regions else
                "No region reached the multi-detector threshold for a tampering signal."
            )

    def _pdf_annotation_regions(self) -> list[dict]:
        """Map PDF annotation rectangles into render-pixel space."""
        structure = self.state.get("pdf_structure") or {}
        out: list[dict] = []
        for page in structure.get("pages", []) or []:
            number = page.get("page")
            box = page.get("media_box")
            size = self.state.get("page_sizes", {}).get(number)
            if not (box and size and len(box) == 4):
                continue
            pdf_w = max(float(box[2]) - float(box[0]), 1.0)
            pdf_h = max(float(box[3]) - float(box[1]), 1.0)
            sx, sy = size[0] / pdf_w, size[1] / pdf_h
            for annot in page.get("annotations", []) or []:
                rect = annot.get("rect") or []
                if len(rect) != 4 or annot.get("subtype") not in {
                        "FreeText", "Square", "Stamp", "Redact", "Ink", "Highlight"}:
                    continue
                x0, y0, x1, y1 = [float(v) for v in rect]
                out.append({
                    "source": "pdf_annotation", "page": number, "confidence": 0.7,
                    "region": {
                        "x": int(min(x0, x1) * sx),
                        "y": int((pdf_h - max(y0, y1)) * sy),
                        "width": int(abs(x1 - x0) * sx), "height": int(abs(y1 - y0) * sy),
                        "unit": "render_px",
                    },
                    "text": annot.get("contents") or annot.get("subtype"),
                })
        return out

    def _stage_consistency(self) -> None:
        with self.stage("consistency") as record:
            extraction = self.state.get("extraction")
            if extraction is None:
                record.status = StageStatus.SKIPPED
                record.message = "No extracted fields to evaluate."
                return
            overrides = self._rule_overrides()
            report = run_consistency(
                extraction, document_type=self.doc.classification_type or "other",
                page_texts=self.state.get("page_texts", {}),
                required_keys=self.state["schema"].required_keys(),
                rule_overrides=overrides,
            )
            self._add(report.findings, record)
            self.state["consistency"] = report
            record.provider = {"key": "consistency-rule-engine", "version": RULES_VERSION}
            record.detail = report.summary()
            record.message = (f"{report.passed_count} check(s) passed, "
                              f"{report.failed_count} failed "
                              f"(rules {RULES_VERSION}).")

    def _rule_overrides(self) -> dict[str, dict]:
        rows = self.db.execute(select(DetectionRule)).scalars().all()
        return {
            r.code: {"enabled": r.enabled, "severity": r.default_severity, "weight": r.weight,
                     "params": r.params or {}, "version": r.version}
            for r in rows
        }

    def _stage_cross_document(self, review_state: dict[str, dict]) -> None:
        with self.stage("cross_document") as record:
            if not self.doc.claim_id:
                record.status = StageStatus.SKIPPED
                record.message = ("The document is not attached to a claim, so there is nothing "
                                  "to compare it against.")
                return
            claim = self.db.get(Claim, self.doc.claim_id)
            siblings = self.db.execute(
                select(Document).where(Document.claim_id == self.doc.claim_id,
                                       Document.deleted_at.is_(None))
            ).scalars().all()
            snapshots = [self._snapshot(d) for d in siblings]
            snapshots = [s for s in snapshots if s.fields]
            claim_payload = None
            if claim:
                claim_payload = {
                    "claim_number": claim.claim_number,
                    "policy_number": claim.policy_number,
                    "customer_name": claim.customer_name,
                    "customer_dob": claim.customer_dob.isoformat() if claim.customer_dob else None,
                    "claimed_amount": str(claim.claimed_amount) if claim.claimed_amount else None,
                    "incident_date": claim.incident_date.isoformat() if claim.incident_date else None,
                }
            report = compare_documents(snapshots, claim=claim_payload)

            # Cross-document findings belong to the whole bundle: regenerate them
            # for every document in the claim so each investigation page agrees.
            for doc in siblings:
                findings_store.clear_findings(
                    self.db, doc.id, kinds=[findings_store.KIND_CROSS_DOCUMENT]
                )
            grouped: dict[str, list[RawFinding]] = {}
            for item in report.findings:
                raw = item.finding
                raw.extras.update({
                    "claim_id": self.doc.claim_id,
                    "document_id": item.document_id,
                    "counterpart_document_id": item.counterpart_document_id,
                    "field_key": item.field_key, "value_a": item.value_a,
                    "value_b": item.value_b, "similarity": item.similarity,
                })
                grouped.setdefault(item.document_id, []).append(raw)
                if item.counterpart_document_id:
                    mirror = replace(raw)
                    mirror.extras = {
                        **raw.extras,
                        "document_id": item.counterpart_document_id,
                        "counterpart_document_id": item.document_id,
                        "value_a": item.value_b, "value_b": item.value_a,
                    }
                    grouped.setdefault(item.counterpart_document_id, []).append(mirror)
            for doc_id, items in grouped.items():
                findings_store.persist(
                    self.db, items, document_id=doc_id, claim_id=self.doc.claim_id,
                    analysis_run_id=self.run.id, review_state=review_state,
                )
            record.findings = len(grouped.get(self.doc.id, []))
            record.detail = report.summary()
            record.message = (
                f"Compared {len(snapshots)} document(s) in claim "
                f"{claim.claim_number if claim else '-'}: "
                f"{record.detail['agreements']} field agreement(s), "
                f"{record.detail['mismatches']} mismatch(es)."
            )

    def _snapshot(self, doc: Document) -> DocumentSnapshot:
        rows = self.db.execute(
            select(ExtractedField).where(ExtractedField.document_id == doc.id)
        ).scalars().all()
        fields = {}
        for row in rows:
            if row.group_name == "line_items":
                continue
            current = fields.get(row.field_key)
            if current and current["confidence"] >= row.confidence:
                continue
            fields[row.field_key] = {
                "value": row.value_normalized, "raw": row.value_raw,
                "confidence": row.confidence, "page": row.page, "bbox": row.bbox,
            }
        return DocumentSnapshot(
            document_id=doc.id, document_ref=doc.document_ref,
            document_type=doc.classification_type or "other",
            label=DOCUMENT_TYPE_LABELS.get(doc.classification_type or "other", "Document"),
            fields=fields,
            uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        )

    def _stage_verification(self) -> None:
        with self.stage("verification") as record:
            extraction = self.state.get("extraction")
            if extraction is None:
                record.status = StageStatus.SKIPPED
                record.message = "No extracted fields to verify."
                return
            plan = PLAN_BY_DOCUMENT_TYPE.get(self.doc.classification_type or "other", [])
            if not plan:
                record.status = StageStatus.SKIPPED
                record.message = ("No trusted-source route is configured for document type "
                                  f"'{self.doc.classification_type or 'other'}'.")
                return
            claim = self.db.get(Claim, self.doc.claim_id) if self.doc.claim_id else None
            values = {f.key: (f.value_normalized or f.value_raw)
                      for f in extraction.fields if (f.value_normalized or f.value_raw)}
            if claim:
                values.setdefault("policy_number", claim.policy_number)
                values.setdefault("customer_name", claim.customer_name)
                if claim.customer_dob:
                    values.setdefault("date_of_birth", claim.customer_dob.isoformat())
            service_date = values.get("treatment_date") or values.get("invoice_date")

            executed, skipped = [], []
            for request_type in plan:
                keys = VERIFICATION_PRIMARY_KEYS.get(request_type, ())
                if not any(values.get(k) for k in keys):
                    skipped.append({"request_type": request_type,
                                    "reason": f"missing {' / '.join(keys)}"})
                    continue
                payload = {k: values[k] for k in REQUEST_PAYLOAD_FIELDS.get(request_type, ())
                           if k in values}
                if service_date:
                    payload["service_date"] = service_date
                if claim and claim.claimed_amount:
                    payload.setdefault("claimed_amount", str(claim.claimed_amount))
                provider = get_verification_provider(request_type)
                request = VerificationRequest(
                    document_id=self.doc.id, claim_id=self.doc.claim_id,
                    analysis_run_id=self.run.id,
                    requested_by_id=self.actor.id if self.actor else None,
                    provider_key=provider.key, provider_label=provider.label,
                    provider_mode=provider.mode, request_type=request_type,
                    request_payload=payload, status="pending", trigger="pipeline",
                )
                self.db.add(request)
                self.db.flush()
                try:
                    response = provider.verify(VerificationQuery(
                        request_type=request_type, payload=payload,
                        document_id=self.doc.id, claim_id=self.doc.claim_id,
                    ))
                    request.status = "completed"
                except ProviderUnavailable as exc:
                    request.status = "unavailable"
                    from app.services.verification.base import VerificationResponse

                    response = VerificationResponse(
                        outcome=VerificationOutcome.UNAVAILABLE,
                        summary=("The verification provider could not be reached. The document is "
                                 "preserved and the check can be retried."),
                        is_demo_data=provider.mode == "demo", error=exc.message,
                    )
                self.db.add(VerificationResult(
                    request_id=request.id, outcome=response.outcome, summary=response.summary,
                    checks=[c.as_dict() for c in response.checks], raw_response=response.raw,
                    latency_ms=response.latency_ms, reference_id=response.reference_id,
                    is_demo_data=response.is_demo_data,
                    data_source_disclaimer=response.disclaimer, error=response.error,
                ))
                executed.append({
                    "request_type": request_type, "provider": provider.label,
                    "mode": provider.mode, "outcome": response.outcome,
                    "summary": response.summary,
                    "failed_checks": [c.label for c in response.failed_checks],
                })
            self.db.flush()
            mismatches = [e for e in executed
                          if e["outcome"] in {VerificationOutcome.MISMATCH,
                                              VerificationOutcome.PARTIAL_MATCH,
                                              VerificationOutcome.NOT_FOUND}]
            demo_used = any(e["mode"] == "demo" for e in executed)
            record.detail = {"executed": executed, "skipped": skipped,
                            "demo_providers_used": demo_used}
            record.provider = {"mode": settings.verification_provider,
                               "demo_data": demo_used}
            record.message = (
                f"{len(executed)} verification request(s) completed, {len(mismatches)} with a "
                f"mismatch or missing record; {len(skipped)} skipped for missing references."
                + (" Demo verification providers answered from the bundled sample registry."
                   if demo_used else "")
            )
            if not executed:
                record.status = StageStatus.SKIPPED

    def _stage_risk(self) -> None:
        with self.stage("risk") as record:
            findings = findings_store.collect(self.db, self.doc.id)
            inputs = [
                risk_engine.FindingInput(
                    code=f.code, category=f.category, severity=f.severity,
                    confidence=f.confidence, title=f.title, kind=f.kind, finding_id=f.finding_id,
                    detector=f.detector, model_version=f.model_version, status=f.status,
                    page=f.page,
                )
                for f in findings
                if f.code != "AIGC_NO_SIGNIFICANT_INDICATORS"
            ]
            verification_inputs = []
            rows = self.db.execute(
                select(VerificationRequest).where(
                    VerificationRequest.document_id == self.doc.id,
                    VerificationRequest.analysis_run_id == self.run.id,
                )
            ).scalars().all()
            for req in rows:
                if not req.result:
                    continue
                verification_inputs.append(risk_engine.VerificationInput(
                    provider_key=req.provider_key, provider_label=req.provider_label,
                    request_type=req.request_type, outcome=req.result.outcome,
                    summary=req.result.summary,
                    failed_checks=[c.get("label") for c in (req.result.checks or [])
                                   if c.get("passed") is False],
                    is_demo_data=req.result.is_demo_data, request_id=req.id,
                ))

            degraded = [s.label for s in self.stages.values()
                        if s.status in {StageStatus.FAILED, StageStatus.UNAVAILABLE}]
            coverage = {
                "stages_completed": [s.key for s in self.stages.values()
                                     if s.status == StageStatus.COMPLETED],
                "degraded_stages": degraded,
                "skipped_stages": [s.key for s in self.stages.values()
                                   if s.status == StageStatus.SKIPPED],
                "pipeline_version": PIPELINE_VERSION,
                "rules_version": RULES_VERSION,
            }
            result = risk_engine.assess(
                inputs, verification_inputs,
                rule_weights=self._risk_weights(), thresholds=self._risk_thresholds(),
                stage_coverage=coverage,
            )
            for prior in self.db.execute(
                select(RiskAssessment).where(RiskAssessment.document_id == self.doc.id,
                                             RiskAssessment.is_superseded.is_(False))
            ).scalars().all():
                prior.is_superseded = True
            assessment = RiskAssessment(
                document_id=self.doc.id, claim_id=self.doc.claim_id,
                analysis_run_id=self.run.id, score=result.score, band=result.band,
                weights_version=result.weights_version,
                signals=[s.as_dict() for s in result.signals],
                category_scores=result.category_scores, top_reasons=result.top_reasons,
                explanation=result.explanation, interpretation_note=result.interpretation_note,
                coverage={**result.coverage, "mitigations": result.mitigations},
            )
            self.db.add(assessment)
            self.doc.risk_score = result.score
            self.doc.risk_band = result.band
            self.db.flush()
            self.state["risk"] = result
            record.provider = {"key": "fraud-risk-engine",
                               "version": result.weights_version}
            record.message = f"{result.band_label} - {result.score}/100. {result.explanation}"
            record.detail = result.as_dict()

    def _risk_weights(self) -> dict[str, float]:
        rows = self.db.execute(select(DetectionRule).where(DetectionRule.enabled.is_(True))).scalars().all()
        return {r.code: r.weight for r in rows}

    def _risk_thresholds(self) -> dict:
        row = self.db.execute(
            select(SystemSetting).where(SystemSetting.key == "risk_thresholds")
        ).scalar_one_or_none()
        if row and isinstance(row.value, dict):
            return row.value
        return dict(risk_engine.DEFAULT_THRESHOLDS)

    # ----------------------------------------------------------------- finalise
    def _finalise(self, persisted_count: int) -> None:
        statuses = {s.key: s.status for s in self.stages.values()}
        failed_critical = [k for k in self.critical
                           if statuses.get(k) in {StageStatus.FAILED, StageStatus.UNAVAILABLE}]
        degraded = [k for k, v in statuses.items()
                    if v in {StageStatus.FAILED, StageStatus.UNAVAILABLE}]

        if self.doc.processing_status == ProcessingStatus.QUARANTINED:
            final = ProcessingStatus.QUARANTINED
            message = ("The upload was quarantined by the security check. The original file is "
                       "retained as evidence and was not analysed further.")
        elif failed_critical:
            final = ProcessingStatus.FAILED
            message = ("Analysis could not complete: "
                       + "; ".join(f"{self.stages[k].label} - {self.stages[k].message}"
                                   for k in failed_critical)
                       + ". The original document is preserved and can be reprocessed.")
        elif degraded:
            final = ProcessingStatus.PARTIAL
            message = ("Document processed with reduced coverage. Degraded stages: "
                       + ", ".join(self.stages[k].label for k in degraded)
                       + ". The original document is preserved and can be reprocessed.")
        else:
            final = ProcessingStatus.ANALYZED
            message = "All analysis stages completed."

        self.doc.processing_status = final
        self.doc.processing_message = message
        if settings.retention_days:
            self.doc.retention_expires_at = (
                (self.doc.uploaded_at or datetime.now(timezone.utc))
                + timedelta(days=settings.retention_days)
            )
        total_findings = sum(s.findings for s in self.stages.values())
        self.run.status = final
        self.run.finished_at = datetime.now(timezone.utc)
        self.run.duration_ms = int(
            (self.run.finished_at - (self.run.started_at or self.run.finished_at)).total_seconds() * 1000
        )
        self.run.findings_count = total_findings
        self.run.error = message if final in {ProcessingStatus.FAILED} else None
        self.run.provider_snapshot = {
            "ocr": self.stages["ocr"].provider,
            "aigc": self.stages["aigc"].provider,
            "verification": self.stages["verification"].provider,
            "malware": self.stages["security_scan"].provider,
            "storage": self.storage.name,
            "pipeline_version": PIPELINE_VERSION,
            "rules_version": RULES_VERSION,
        }
        self._flush_stages()
        self._update_claim()

        audit.record(
            self.db,
            action=(AuditAction.ANALYSIS_COMPLETED if final != ProcessingStatus.FAILED
                    else AuditAction.ANALYSIS_FAILED),
            resource_type="document", resource_id=self.doc.id, actor=self.actor,
            summary=(f"Analysis {final} for {self.doc.document_ref}: {total_findings} finding(s), "
                     f"risk {self.doc.risk_score}/100 ({self.doc.risk_band})."),
            after={"processing_status": final, "risk_score": self.doc.risk_score,
                   "risk_band": self.doc.risk_band, "findings": total_findings,
                   "persisted_findings": persisted_count},
            metadata={"analysis_run_id": self.run.id, "pipeline_version": PIPELINE_VERSION,
                      "rules_version": RULES_VERSION,
                      "stage_status": statuses},
        )

    def _update_claim(self) -> None:
        if not self.doc.claim_id:
            return
        claim = self.db.get(Claim, self.doc.claim_id)
        if claim is None:
            return
        docs = self.db.execute(
            select(Document).where(Document.claim_id == claim.id,
                                   Document.deleted_at.is_(None))
        ).scalars().all()
        scores = [d.risk_score for d in docs if d.risk_score is not None]
        previous_status = claim.status
        if scores:
            claim.risk_score = max(scores)
            claim.risk_band = risk_engine.band_for_score(
                claim.risk_score, self._risk_thresholds()
            )
        pending = any(d.processing_status in {ProcessingStatus.QUEUED,
                                             ProcessingStatus.PROCESSING} for d in docs)
        all_human_verified = bool(docs) and all(
            d.verification_state == VerificationState.VERIFIED for d in docs
        )
        if pending:
            claim.status = ClaimStatus.PROCESSING
        elif claim.status in {ClaimStatus.SUBMITTED, ClaimStatus.PROCESSING}:
            # "Verified" is a human verdict. Automated analysis can clear a claim
            # for review but never declare it verified - that requires every
            # document to have been marked verified by a named reviewer.
            claim.status = (ClaimStatus.VERIFIED if all_human_verified
                            else ClaimStatus.REVIEW_REQUIRED)
        if previous_status != claim.status:
            audit.record(
                self.db, action=AuditAction.CLAIM_STATUS_CHANGED, resource_type="claim",
                resource_id=claim.id, actor=self.actor,
                summary=(f"Claim {claim.claim_number} moved to {claim.status} after analysis of "
                         f"{self.doc.document_ref}."),
                before={"status": previous_status}, after={"status": claim.status,
                                                           "risk_score": claim.risk_score},
                metadata={"automated": True, "trigger": "analysis_pipeline"},
            )
        # A high-concern document opens an investigation case automatically. This
        # is triage only: the case is unresolved until a human records a decision.
        if claim.risk_band == RiskBand.HIGH_CONCERN:
            existing = self.db.execute(
                select(Investigation).where(
                    Investigation.claim_id == claim.id,
                    Investigation.status != InvestigationStatus.CLOSED,
                )
            ).scalars().first()
            if existing is None:
                case_number = f"INV-{datetime.now(timezone.utc).year}-{claim.claim_number[-6:]}"
                investigator = self._least_loaded_investigator()
                self.db.add(Investigation(
                    case_number=case_number, claim_id=claim.id, document_id=self.doc.id,
                    title=f"High-concern analysis on {claim.claim_number}",
                    status=InvestigationStatus.OPEN, priority="high",
                    assigned_to_id=investigator.id if investigator else None,
                    opened_by_id=self.actor.id if self.actor else None,
                    opened_at=datetime.now(timezone.utc),
                    risk_score_at_open=claim.risk_score,
                    summary=(self.state["risk"].explanation
                             if self.state.get("risk") else None),
                    context={"opened_by": "analysis_pipeline",
                             "trigger_document": self.doc.document_ref},
                ))
                self.db.flush()
                audit.record(
                    self.db, action=AuditAction.INVESTIGATION_CREATED,
                    resource_type="investigation", resource_id=case_number, actor=self.actor,
                    summary=(f"Investigation {case_number} opened automatically for "
                             f"{claim.claim_number} (risk {claim.risk_score}/100)."),
                    metadata={"automated": True, "assigned_to":
                              investigator.email if investigator else None},
                )

    def _least_loaded_investigator(self) -> User | None:
        from app.core.rbac import Role

        investigators = self.db.execute(
            select(User).where(User.role_name == Role.FRAUD_INVESTIGATOR,
                               User.is_active.is_(True), User.deleted_at.is_(None))
        ).scalars().all()
        if not investigators:
            return None
        loads = []
        for user in investigators:
            open_cases = self.db.execute(
                select(Investigation).where(
                    Investigation.assigned_to_id == user.id,
                    Investigation.status != InvestigationStatus.CLOSED,
                )
            ).scalars().all()
            loads.append((len(open_cases), user.created_at, user))
        loads.sort(key=lambda t: (t[0], t[1]))
        return loads[0][2]


def run_analysis(
    db: Session, document_id: str, *, actor: User | None = None, run_id: str | None = None,
    reprocess_of: str | None = None,
) -> AnalysisRun:
    document = db.get(Document, document_id)
    if document is None:
        raise AppError(f"Document {document_id} no longer exists.")
    run = db.get(AnalysisRun, run_id) if run_id else None
    if run is None:
        run = AnalysisRun(
            document_id=document.id, claim_id=document.claim_id,
            triggered_by_id=actor.id if actor else None,
            status=ProcessingStatus.QUEUED, pipeline_version=PIPELINE_VERSION,
            rules_version=RULES_VERSION, queue_mode=settings.queue_mode,
            reprocess_of_id=reprocess_of,
            stages=[StageRecord(key=key, label=label).as_dict()
                    for key, label, _ in STAGE_DEFINITIONS],
        )
        db.add(run)
        db.flush()
    pipeline = AnalysisPipeline(db, document, run, actor=actor)
    return pipeline.execute()
