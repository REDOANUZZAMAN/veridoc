"""Static seed content: roles, users, rules, providers, settings.

Deterministic by design - identifiers are derived with uuid5 from fixed names so
re-seeding is idempotent and demo links stay stable across rebuilds.
"""
from __future__ import annotations

import uuid

from app.core.rbac import ROLE_DESCRIPTIONS, ROLE_LABELS, Role, permissions_for
from app.db.enums import ProviderKind, Severity

NAMESPACE = uuid.UUID("3f2a6c1e-8b7d-4f0a-9c21-7de5b4a91c00")


def stable_id(kind: str, key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{key}"))


def role_rows() -> list[dict]:
    return [
        {
            "id": stable_id("role", role),
            "name": str(role),
            "label": ROLE_LABELS[role],
            "description": ROLE_DESCRIPTIONS[role],
            "permissions": sorted(str(p) for p in permissions_for(role)),
            "is_system": True,
        }
        for role in Role
    ]


DEMO_USERS = [
    {"email": "admin@veridoc.example", "full_name": "Rhea Kapoor", "role": Role.ADMIN,
     "job_title": "Platform Administrator", "team": "Financial Crime Technology"},
    {"email": "investigator@veridoc.example", "full_name": "Daniel Osei",
     "role": Role.FRAUD_INVESTIGATOR, "job_title": "Senior Fraud Investigator",
     "team": "Special Investigations Unit"},
    {"email": "investigator2@veridoc.example", "full_name": "Lena Brückner",
     "role": Role.FRAUD_INVESTIGATOR, "job_title": "Fraud Investigator",
     "team": "Special Investigations Unit"},
    {"email": "claims@veridoc.example", "full_name": "Tomás Ferreira",
     "role": Role.CLAIMS_OFFICER, "job_title": "Claims Officer", "team": "Health Claims"},
    {"email": "claims2@veridoc.example", "full_name": "Aisha Nour",
     "role": Role.CLAIMS_OFFICER, "job_title": "Motor Claims Officer", "team": "Motor Claims"},
    {"email": "reviewer@veridoc.example", "full_name": "Henrik Solberg",
     "role": Role.REVIEWER, "job_title": "Quality Reviewer", "team": "Assurance"},
]


# --------------------------------------------------------------------------- #
# Detection rules / risk weights
# --------------------------------------------------------------------------- #
# (code, name, category, severity, weight, description)
DETECTOR_RULES: list[tuple[str, str, str, str, float, str]] = [
    # --- metadata provenance ---
    ("PDF_MODDATE_BEFORE_CREATION", "PDF modified before creation", "metadata",
     Severity.HIGH, 16.0,
     "The PDF reports a modification date earlier than its creation date."),
    ("PDF_EDITED_AFTER_CREATION", "PDF re-saved after creation", "metadata",
     Severity.MEDIUM, 9.0, "The document was saved again well after it was produced."),
    ("PDF_IMAGE_EDITOR_PRODUCER", "Produced by an image or design editor", "metadata",
     Severity.HIGH, 17.0,
     "Transactional documents are not normally exported by raster/design editors."),
    ("PDF_MANIPULATION_TOOLING", "PDF manipulation tooling in metadata", "metadata",
     Severity.LOW, 6.0, "Merge/split/re-save tooling named in the metadata."),
    ("PDF_PRODUCER_CREATOR_MISMATCH", "Creator and Producer disagree", "metadata",
     Severity.LOW, 6.0, "The document was exported by one tool and re-saved by another."),
    ("PDF_FUTURE_TIMESTAMP", "PDF timestamp in the future", "metadata", Severity.MEDIUM, 10.0,
     "A metadata timestamp is later than the processing time."),
    ("PDF_METADATA_ABSENT", "No PDF metadata", "metadata", Severity.LOW, 5.0,
     "The document information dictionary is empty."),
    ("PDF_PRODUCER_ABSENT", "No producing software recorded", "metadata", Severity.LOW, 5.0,
     "Originating software cannot be established from metadata."),
    ("IMG_EDITOR_SOFTWARE_TAG", "EXIF names an editing application", "metadata",
     Severity.HIGH, 17.0, "The image was opened and re-saved by an editor."),
    ("IMG_EXIF_TIMESTAMP_DRIFT", "Image re-saved after capture", "metadata",
     Severity.MEDIUM, 11.0, "File modification time is well after capture time."),
    ("IMG_EXIF_FUTURE_TIMESTAMP", "EXIF timestamp in the future", "metadata",
     Severity.MEDIUM, 10.0, "Capture timestamp is later than now."),
    ("IMG_EXIF_STRIPPED", "No EXIF on a photographic format", "metadata", Severity.LOW, 5.0,
     "Provenance metadata is absent; common for exports and messaging apps."),

    # --- structural / pixel forensics ---
    ("PDF_INCREMENTAL_UPDATE", "Incremental PDF revision present", "forensics",
     Severity.MEDIUM, 13.0, "Content was appended after the original save."),
    ("PDF_TRAILING_DATA", "Data after the final %%EOF", "forensics", Severity.MEDIUM, 11.0,
     "Bytes after the end-of-file marker can carry an earlier revision."),
    ("PDF_CONTENT_ANNOTATIONS", "Annotations overlay page content", "forensics",
     Severity.MEDIUM, 14.0, "A value can display differently from the document body."),
    ("PDF_MIXED_FONT_EMBEDDING", "Mixed embedded and system fonts", "forensics",
     Severity.MEDIUM, 12.0, "Typical of text added by a different tool."),
    ("PDF_TEXT_FONT_MIX_IN_LINE", "Font changes inside a text line", "forensics",
     Severity.HIGH, 19.0,
     "Exact measurement: characters drawn with a different font resource from their line."),
    ("PDF_FONT_DIVERSITY", "High typeface count on one page", "forensics", Severity.LOW, 5.0,
     "May indicate content assembled from multiple sources."),
    ("PDF_MIXED_IMAGE_COMPRESSION", "Embedded images use different codecs", "forensics",
     Severity.MEDIUM, 12.0, "A pasted region often arrives with its own encoding."),
    ("PDF_MASKED_IMAGE_OVERLAY", "Masked image overlay", "forensics", Severity.MEDIUM, 11.0,
     "Mechanism used to place stamps or signatures over existing content."),
    ("PDF_MIXED_BIT_DEPTH", "Mixed image bit depths", "forensics", Severity.LOW, 5.0,
     "Images appear to come from different sources."),
    ("IMG_ELA_LOCAL_ANOMALY", "Localised compression-response anomaly", "forensics",
     Severity.MEDIUM, 13.0, "Error level analysis flags a spatially clustered anomaly."),
    ("IMG_COPY_MOVE_REGION", "Duplicated image region", "forensics", Severity.HIGH, 16.0,
     "Keypoints repeat with a consistent displacement."),
    ("IMG_COMPRESSION_INCONSISTENCY", "Compression quality inconsistency", "forensics",
     Severity.MEDIUM, 13.0, "Parts of the page carry a different compression history."),
    ("IMG_NOISE_INCONSISTENCY", "Sensor-noise inconsistency", "forensics", Severity.MEDIUM, 10.0,
     "Local noise floor varies more than a single capture would produce."),
    ("IMG_RESAMPLING_ARTIFACTS", "Resampling periodicity", "forensics", Severity.MEDIUM, 9.0,
     "Interpolation trace from rescaling or rotation."),
    ("IMG_LOW_JPEG_QUALITY", "Low JPEG quality limits analysis", "forensics", Severity.LOW, 4.0,
     "Heavy compression reduces forensic resolution; findings carry less weight."),
    ("IMG_NONSTANDARD_QUANT_TABLE", "Non-standard quantisation table", "forensics",
     Severity.LOW, 6.0, "Points at a specific editor rather than a camera pipeline."),
    ("TXT_STROKE_WEIGHT_ANOMALY", "Stroke weight inconsistent in a line", "forensics",
     Severity.MEDIUM, 12.0, "Different typeface, weight or rendering path for one word."),
    ("TXT_BASELINE_ANOMALY", "Text baseline misalignment", "forensics", Severity.MEDIUM, 10.0,
     "A word sits off the baseline shared by its line."),
    ("TXT_GLYPH_SIZE_ANOMALY", "Glyph size inconsistent in a line", "forensics",
     Severity.LOW, 8.0, "Replacement text set at a slightly different point size."),
    ("TXT_LOW_CONFIDENCE_ISLAND", "Low-confidence text inside clean text", "forensics",
     Severity.LOW, 7.0, "Recognition uncertainty isolated to one token."),

    # --- security ---
    ("SEC_MALWARE_SIGNATURE", "Malware signature in upload", "security", Severity.CRITICAL,
     30.0, "The upload is quarantined and not analysed further."),
    ("SEC_ACTIVE_CONTENT", "Active content in upload", "security", Severity.HIGH, 18.0,
     "Executable constructs found by static inspection."),
    ("PDF_EMBEDDED_JAVASCRIPT", "Embedded JavaScript", "security", Severity.HIGH, 20.0,
     "Script content can change what a form displays."),
    ("PDF_EMBEDDED_FILES", "Embedded file attachments", "security", Severity.MEDIUM, 12.0,
     "Attachments are not part of the visible pages."),

    # --- synthetic media ---
    ("AIGC_SYNTHETIC_INDICATORS", "Synthetic-media indicators present", "aigc",
     Severity.MEDIUM, 13.0,
     "Probabilistic indicator. Must be corroborated by provenance or issuer verification."),

    # --- tampering correlation ---
    ("TAMPER_EDITED_AMOUNT", "Potentially edited amount", "tampering", Severity.HIGH, 24.0,
     "Multiple independent detectors agree on a region covering a monetary value."),
    ("TAMPER_MODIFIED_DATE", "Potentially modified date", "tampering", Severity.HIGH, 21.0,
     "Region-level agreement over a date value."),
    ("TAMPER_ALTERED_IDENTIFIER", "Potentially altered reference", "tampering",
     Severity.HIGH, 20.0, "Region-level agreement over an identifier."),
    ("TAMPER_REPLACED_NAME", "Potentially replaced name", "tampering", Severity.HIGH, 20.0,
     "Region-level agreement over a party name."),
    ("TAMPER_COPY_PASTE_REGION", "Duplicated (copy/paste) region", "tampering",
     Severity.HIGH, 19.0, "A region repeats within the same page."),
    ("TAMPER_ADDED_TEXT", "Potentially added text", "tampering", Severity.MEDIUM, 16.0,
     "Text appears to have been introduced into an existing document."),
    ("TAMPER_OVERLAY_ANNOTATION", "Value overlaid by an annotation", "tampering",
     Severity.HIGH, 20.0, "The rendered value differs from the underlying content stream."),
    ("TAMPER_FONT_SUBSTITUTION", "Inconsistent font characteristics", "tampering",
     Severity.MEDIUM, 15.0, "Typography of one token departs from its line."),
    ("TAMPER_IMAGE_REPLACEMENT", "Possible replaced image object", "tampering",
     Severity.HIGH, 19.0, "An embedded raster appears to have been substituted."),
    ("TAMPER_SIGNATURE_OR_STAMP", "Signature or stamp area anomaly", "tampering",
     Severity.HIGH, 19.0, "Anomalies clustered in the attestation area of the document."),
    ("TAMPER_REGION_ANOMALY", "Unattributed region anomaly", "tampering", Severity.MEDIUM, 12.0,
     "Detectors agree on a region that does not cover an extracted field."),
    ("TAMPER_REPLACED_TEXT", "Potentially replaced text", "tampering", Severity.MEDIUM, 16.0,
     "Region-level agreement over a text value."),
    ("TAMPER_EDITED_VALUE", "Potentially edited value", "tampering", Severity.MEDIUM, 16.0,
     "Region-level agreement over a numeric value."),

    # --- duplicate content ---
    ("DOC_DUPLICATE_CONTENT_HASH", "Byte-identical duplicate upload", "consistency",
     Severity.HIGH, 18.0, "The same file has been submitted before - possible duplicate billing."),
    ("CLS_UNRECOGNISED_DOCUMENT_TYPE", "Document type undetermined", "consistency",
     Severity.LOW, 5.0, "Type-specific rules and verification routes were not applied."),

    # --- cross-document ---
    ("XDOC_TOTAL_MISMATCH", "Total amount differs between documents", "cross_document",
     Severity.HIGH, 24.0, "Documents in one claim disagree on the amount."),
    ("XDOC_PATIENT_NAME_MISMATCH", "Patient name differs between documents", "cross_document",
     Severity.HIGH, 21.0, "Documents in one claim disagree on the patient."),
    ("XDOC_POLICY_NUMBER_MISMATCH", "Policy number differs between documents",
     "cross_document", Severity.HIGH, 22.0, "Documents cite different policies."),
    ("XDOC_TREATMENT_DATE_MISMATCH", "Treatment date differs between documents",
     "cross_document", Severity.HIGH, 20.0, "Documents disagree on the date of service."),
    ("XDOC_HOSPITAL_NAME_MISMATCH", "Provider differs between documents", "cross_document",
     Severity.MEDIUM, 16.0, "Documents cite different providers."),
    ("XDOC_INVOICE_NUMBER_MISMATCH", "Invoice reference differs between documents",
     "cross_document", Severity.MEDIUM, 15.0, "Documents cite different invoice references."),
    ("XDOC_CLAIM_TOTAL_MISMATCH", "Document total differs from the claim record",
     "cross_document", Severity.HIGH, 23.0,
     "Supporting evidence does not corroborate the submitted claim amount."),
    ("XDOC_CLAIM_POLICY_NUMBER_MISMATCH", "Policy number differs from the claim record",
     "cross_document", Severity.HIGH, 22.0, "The document cites a different policy."),
    ("XDOC_CLAIM_CUSTOMER_NAME_MISMATCH", "Customer name differs from the claim record",
     "cross_document", Severity.MEDIUM, 17.0, "The document names a different party."),

    # --- verification ---
    ("VERIFY_POLICY_LOOKUP_MISMATCH", "Policy verification mismatch", "verification",
     Severity.HIGH, 28.0, "The insurer record disagrees with the submitted document."),
    ("VERIFY_POLICY_LOOKUP_NOT_FOUND", "Policy not found at source", "verification",
     Severity.HIGH, 27.0, "The policy reference is unknown to the source system."),
    ("VERIFY_POLICY_LOOKUP_PARTIAL_MATCH", "Policy partially verified", "verification",
     Severity.MEDIUM, 18.0, "Some policy checks passed and others failed."),
    ("VERIFY_INVOICE_LOOKUP_MISMATCH", "Invoice verification mismatch", "verification",
     Severity.HIGH, 28.0, "The issuer's record of this invoice differs."),
    ("VERIFY_INVOICE_LOOKUP_NOT_FOUND", "Invoice not found at issuer", "verification",
     Severity.HIGH, 27.0, "The issuer has no record of this invoice reference."),
    ("VERIFY_INVOICE_LOOKUP_PARTIAL_MATCH", "Invoice partially verified", "verification",
     Severity.MEDIUM, 19.0, "Some invoice checks passed and others failed."),
    ("VERIFY_PROVIDER_LOOKUP_MISMATCH", "Provider verification mismatch", "verification",
     Severity.HIGH, 24.0, "Provider accreditation or network status disagrees."),
    ("VERIFY_PROVIDER_LOOKUP_NOT_FOUND", "Provider not in registry", "verification",
     Severity.HIGH, 25.0, "No accreditation record exists for the named provider."),
    ("VERIFY_PROVIDER_LOOKUP_PARTIAL_MATCH", "Provider partially verified", "verification",
     Severity.MEDIUM, 16.0, "Provider exists but some attributes disagree."),
    ("VERIFY_IDENTITY_LOOKUP_MISMATCH", "Identity verification mismatch", "verification",
     Severity.CRITICAL, 30.0, "The identity register disagrees with the document."),
    ("VERIFY_IDENTITY_LOOKUP_NOT_FOUND", "Identity document not on record", "verification",
     Severity.HIGH, 27.0, "The document number is unknown to the register."),
    ("VERIFY_IDENTITY_LOOKUP_PARTIAL_MATCH", "Identity partially verified", "verification",
     Severity.HIGH, 21.0, "Some identity checks failed."),
    ("VERIFY_VEHICLE_LOOKUP_MISMATCH", "Vehicle verification mismatch", "verification",
     Severity.HIGH, 26.0, "The vehicle register disagrees with the document."),
    ("VERIFY_VEHICLE_LOOKUP_NOT_FOUND", "Vehicle not on record", "verification",
     Severity.HIGH, 25.0, "The registration is unknown to the register."),
    ("VERIFY_VEHICLE_LOOKUP_PARTIAL_MATCH", "Vehicle partially verified", "verification",
     Severity.MEDIUM, 19.0, "Vehicle exists but attributes or markers disagree."),
    ("VERIFY_PAYMENT_LOOKUP_MISMATCH", "Payment verification mismatch", "verification",
     Severity.HIGH, 26.0, "The settlement record disagrees with the document."),
    ("VERIFY_PAYMENT_LOOKUP_NOT_FOUND", "Payment reference not found", "verification",
     Severity.HIGH, 24.0, "No settlement exists for this reference."),
    ("VERIFY_PAYMENT_LOOKUP_PARTIAL_MATCH", "Payment partially verified", "verification",
     Severity.MEDIUM, 18.0, "Payment exists but amount or status disagrees."),
]


def provider_rows() -> list[dict]:
    return [
        # --- OCR ---
        {"kind": ProviderKind.OCR, "key": "hybrid",
         "label": "Hybrid (PDF text layer -> Tesseract)", "is_active": True, "is_demo": False,
         "description": ("Uses the embedded text layer when a PDF has one - exact characters and "
                         "exact coordinates - and falls back to Tesseract for scans and photos."),
         "credential_env_keys": [], "model_name": "hybrid", "model_version": "1.1"},
        {"kind": ProviderKind.OCR, "key": "tesseract", "label": "Tesseract OCR (local)",
         "is_active": False, "is_demo": False,
         "description": "Pixel OCR for every page, regardless of an available text layer.",
         "credential_env_keys": [], "model_name": "tesseract", "model_version": "5.x"},
        {"kind": ProviderKind.OCR, "key": "pdf_text", "label": "PDF text-layer extractor",
         "is_active": False, "is_demo": False,
         "description": "Embedded text only. Returns nothing for scanned documents.",
         "credential_env_keys": [], "model_name": "pdfplumber", "model_version": "1.0"},
        {"kind": ProviderKind.OCR, "key": "demo_fixture",
         "label": "Demo Fixture OCR Provider (replay)", "is_active": False, "is_demo": True,
         "description": ("Replays stored OCR fixtures for offline demos and CI. Performs no "
                         "recognition."),
         "credential_env_keys": [], "model_name": "fixture", "model_version": "1.0"},

        # --- AIGC ---
        {"kind": ProviderKind.AIGC, "key": "demo_heuristic",
         "label": "Demo Heuristic Synthetic-Media Analyser", "is_active": True, "is_demo": True,
         "description": ("Deterministic feature heuristics (spectral roll-off, noise uniformity, "
                         "channel coupling, gradient kurtosis, provenance, glyph regularity). "
                         "Explainable and reproducible, but NOT a trained classifier - results "
                         "are labelled as demo everywhere they appear."),
         "credential_env_keys": [], "model_name": "veridoc-demo-heuristic",
         "model_version": "0.4.0"},
        {"kind": ProviderKind.AIGC, "key": "remote_http",
         "label": "Remote synthetic-media detection API", "is_active": False, "is_demo": False,
         "description": ("Production seam. POSTs each page raster to a vendor endpoint and maps "
                         "the response into the platform's finding contract."),
         "credential_env_keys": ["AIGC_REMOTE_URL", "AIGC_REMOTE_API_KEY"],
         "model_name": "vendor", "model_version": "unknown"},

        # --- verification ---
        {"kind": ProviderKind.VERIFICATION, "key": "demo_policy",
         "label": "Demo Verification Provider - Insurance Policy Registry",
         "is_active": True, "is_demo": True,
         "description": ("Answers policy lookups from the bundled sample registry. No insurer is "
                         "contacted."),
         "credential_env_keys": [], "model_name": None, "model_version": None},
        {"kind": ProviderKind.VERIFICATION, "key": "demo_hospital",
         "label": "Demo Verification Provider - Provider Accreditation Registry",
         "is_active": True, "is_demo": True,
         "description": "Answers provider accreditation lookups from the sample registry.",
         "credential_env_keys": []},
        {"kind": ProviderKind.VERIFICATION, "key": "demo_invoice",
         "label": "Demo Verification Provider - Invoice / Billing Registry",
         "is_active": True, "is_demo": True,
         "description": "Answers invoice lookups from the sample registry.",
         "credential_env_keys": []},
        {"kind": ProviderKind.VERIFICATION, "key": "demo_gov_id",
         "label": "Demo Verification Provider - Government ID Registry",
         "is_active": True, "is_demo": True,
         "description": "Answers identity-document lookups from the sample registry.",
         "credential_env_keys": []},
        {"kind": ProviderKind.VERIFICATION, "key": "demo_vehicle",
         "label": "Demo Verification Provider - Vehicle Registry",
         "is_active": True, "is_demo": True,
         "description": "Answers vehicle lookups from the sample registry.",
         "credential_env_keys": []},
        {"kind": ProviderKind.VERIFICATION, "key": "demo_payment",
         "label": "Demo Verification Provider - Payment / Settlement Registry",
         "is_active": True, "is_demo": True,
         "description": "Answers settlement lookups from the sample registry.",
         "credential_env_keys": []},
        {"kind": ProviderKind.VERIFICATION, "key": "remote_http",
         "label": "Production Verification API", "is_active": False, "is_demo": False,
         "description": ("Production seam for real insurer, hospital, government and banking "
                         "endpoints."),
         "credential_env_keys": ["VERIFICATION_REMOTE_URL", "VERIFICATION_REMOTE_API_KEY"]},

        # --- storage / malware ---
        {"kind": ProviderKind.STORAGE, "key": "local", "label": "Local filesystem volume",
         "is_active": True, "is_demo": False,
         "description": ("Originals and derived artifacts in separate directories; originals are "
                         "written read-only."),
         "credential_env_keys": []},
        {"kind": ProviderKind.STORAGE, "key": "s3", "label": "S3-compatible object storage",
         "is_active": False, "is_demo": False,
         "description": ("MinIO, AWS S3, Supabase Storage, R2. Separate buckets for originals and "
                         "artifacts, optional SSE."),
         "credential_env_keys": ["S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID",
                                 "S3_SECRET_ACCESS_KEY"]},
        {"kind": ProviderKind.MALWARE, "key": "heuristic",
         "label": "Built-in heuristic static scanner", "is_active": True, "is_demo": False,
         "description": ("Signature-free static checks for active content, polyglots and "
                         "executables, plus the EICAR test signature."),
         "credential_env_keys": [], "model_version": "1.2.0"},
        {"kind": ProviderKind.MALWARE, "key": "clamav", "label": "ClamAV daemon (clamd)",
         "is_active": False, "is_demo": False,
         "description": "INSTREAM scanning against a clamd service.",
         "credential_env_keys": ["CLAMAV_HOST", "CLAMAV_PORT"]},
    ]


SYSTEM_SETTINGS = [
    {"key": "risk_thresholds", "label": "Risk band thresholds",
     "value": {"review_recommended": 40, "high_concern": 75},
     "description": ("Score at which a document moves from Low Concern to Review Recommended, and "
                     "from there to High Concern. Raising 'high_concern' reduces auto-opened "
                     "investigations.")},
    {"key": "retention", "label": "Retention policy",
     "value": {"document_days": 365, "artifact_days": 180, "audit_days": 2555,
               "purge_requires_soft_delete": True},
     "description": ("Derived artifacts are purged before originals; originals are only removed "
                     "once a document has been soft-deleted, so the evidence chain is never "
                     "broken by a scheduled job.")},
    {"key": "review_policy", "label": "Human review policy",
     "value": {"require_reason_on_confirm": True, "require_reason_on_dismiss": True,
               "block_approval_with_open_high_findings": True,
               "min_reason_length": 10},
     "description": ("Machine findings must be adjudicated by a named human before a claim can be "
                     "approved. These settings are enforced server side.")},
    {"key": "analysis_policy", "label": "Analysis policy",
     "value": {"pixel_analysis_page_limit": 12, "ocr_page_limit": 30,
               "auto_open_investigation_on_high_concern": True,
               "preserve_review_state_on_reprocess": True},
     "description": "Coverage limits and automation behaviour for the analysis pipeline."},
    {"key": "privacy_policy", "label": "Privacy controls",
     "value": {"pii_aware_logging": True, "audit_field_redaction": True,
               "signed_url_ttl_seconds": 300, "public_document_access": False},
     "description": ("Document bodies are never logged; audit entries store structured field "
                     "diffs with sensitive keys redacted."),
     },
]
