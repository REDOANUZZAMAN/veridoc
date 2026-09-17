# Architecture

## Repository layout

```
veridoc/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI app factory: middleware, handlers, router
│   │   ├── core/                   config, security, RBAC, deps, errors, logging, rate limit
│   │   ├── db/
│   │   │   ├── models/             25 tables (see "Data model")
│   │   │   ├── enums.py            canonical status/severity/category strings
│   │   │   ├── seed.py             schema bootstrap + deterministic demo seeding
│   │   │   ├── seed_data.py        roles, users, 99 rules, 17 provider configs, settings
│   │   │   ├── demo_documents.py   renders demo PDFs/rasters with anomalies baked in
│   │   │   └── demo_scenarios.py   10 claims / 22 documents / scripted review history
│   │   ├── services/
│   │   │   ├── pipeline.py         the 14-stage orchestrator
│   │   │   ├── validation.py       pre-ingest content validation
│   │   │   ├── render.py           page rasterisation into the artifacts scope
│   │   │   ├── findings_store.py   persistence + one uniform read model for 5 finding tables
│   │   │   ├── audit.py            append-only hash-chained audit trail
│   │   │   ├── storage/            StorageProvider: local filesystem, S3-compatible
│   │   │   ├── ocr/                OcrProvider: hybrid, tesseract, pdf_text, demo fixture
│   │   │   ├── classify/           lexical + structural document classifier
│   │   │   ├── extract/            declarative schema, normalisation, extraction engine
│   │   │   ├── forensics/          pdf, pdf_images, image, image_meta, text_layout
│   │   │   ├── aigc/               AigcProvider: demo heuristic, remote HTTP
│   │   │   ├── tampering/          multi-detector correlation layer
│   │   │   ├── consistency/        20-rule engine with admin-tunable configuration
│   │   │   ├── crossdoc/           claim-bundle comparison with pairing policies
│   │   │   ├── verification/       VerificationProvider: 6 demo providers, remote HTTP
│   │   │   ├── risk/               transparent scoring engine
│   │   │   ├── malware/            MalwareScanner: heuristic static, ClamAV
│   │   │   └── reports/            ReportLab PDF generation
│   │   ├── api/routes/             auth, documents, claims, verification, investigations,
│   │   │                           reports, audit, users, dashboard, admin, health
│   │   ├── schemas/                Pydantic request/response models
│   │   └── workers/                RQ queue, tasks, worker entry point
│   ├── alembic/                    migrations (initial schema generated from the models)
│   └── tests/                      174 tests against real PostgreSQL + real storage
└── frontend/
    └── src/
        ├── app/
        │   ├── (app)/              authenticated console: 11 screens
        │   ├── api/auth/*          login/logout route handlers (set the httpOnly cookie)
        │   ├── api/be/[...path]/   authenticated reverse proxy to the API
        │   └── login/              sign-in
        ├── components/
        │   ├── ui/                 21 shadcn-style primitives on Radix
        │   ├── layout/             shell, sidebar, nav matrix, theme, user menu
        │   ├── shared/             risk/severity/status chips, pipeline timeline, legends
        │   ├── dashboard/          validated chart palette, chart container, charts
        │   ├── documents/          viewer, workstation, 8 evidence panels, review actions
        │   └── claims/             claim creation, decision, assignment, notes
        └── lib/                    server API client, browser proxy client, session, formatting
```

## Data model

25 tables. The shape follows the evidence, not the screens.

| Group | Tables |
|---|---|
| Identity | `roles`, `users` |
| Claim | `claims` |
| Document | `documents`, `document_pages`, `document_metadata`, `ocr_results`, `extracted_fields` |
| Analysis | `analysis_runs`, `risk_assessments` |
| Findings | `forensic_findings`, `aigc_findings`, `tampering_findings`, `consistency_findings`, `cross_document_findings` |
| Verification | `verification_requests`, `verification_results` |
| Human process | `investigations`, `investigation_notes`, `review_actions` |
| Output | `reports` |
| Governance | `audit_logs`, `detection_rules`, `provider_configs`, `system_settings` |

### Why findings live in five tables

They share one evidence contract — `finding_id, category, severity, confidence, page, region,
description, evidence, detector, model_version, created_at` — through a common mixin, but they are
stored separately because their provenance and their retention differ. A deterministic rule finding
and a model inference are not the same kind of claim about the world, and a cross-document finding
belongs to a *bundle* rather than to a single document (it carries `claim_id` and
`counterpart_document_id`).

`services/findings_store.py` is the only module that knows the mapping. It exposes one uniform read
model to the API, the risk engine and the report generator, so nothing downstream has to care.

### Soft deletes and retention

`documents` and `claims` carry `deleted_at`; listings filter on it. The retention job purges derived
artifacts once past the window, and only removes an original when the document has *also* been
soft-deleted — a scheduled job can never silently destroy evidence.

## Pipeline internals

`services/pipeline.py` runs 14 stages through a context manager that records, per stage: status,
start, finish, duration, provider snapshot, message, finding count and a stage-specific detail blob.

Error isolation is by stage:

- `ProviderUnavailable` → `unavailable` (retryable; the document is untouched)
- any other exception → `failed`, with the exception type recorded
- a stage whose inputs are absent → `skipped` with a stated reason

Stage classification decides the run's outcome: a failed *critical* stage (validation, security,
render, OCR, classification, extraction, risk) fails the run; a failed non-critical stage marks it
`partial`. Either way `processing_message` tells the operator the original is preserved and can be
reprocessed, and the risk assessment records the degraded stages so the report can state that the
absence of findings in those areas is omission, not evidence.

### Notable decisions

**Pixel forensics do not run on vector PDF page renders.** ELA, noise residual, compression history
and resampling only carry information where there is a real capture or compression history. A vector
render has none — measuring it measures the renderer. For PDFs the raster suite therefore runs over
*embedded* raster objects (where a scan or a pasted graphic actually lives), and when a page has
none, the stage says so explicitly rather than reporting noise. Structural, metadata, font and
typography analysis carry the forensic signal for digital PDFs.

**Region significance is established statistically, not by thresholding blocks.** A document's
blocks vary enormously — body text, blank paper, a logo — so no single block is ever a significant
outlier, and thresholding them either misses real edits or floods the report. A sliding window runs
a two-sample comparison against the rest of the page, over content blocks only, and requires both
statistical strength and a minimum effect size.

**Two detectors are measured but deliberately not raised as signals on text-heavy rasters.**
Resampling periodicity and JPEG lattice energy are confounded by the regular line pitch and stroke
gradients of print: on a document image they fire on essentially everything. Both are computed and
kept in the evidence blob as context, with `signal_suppressed_for_text: true` and the reason,
because a detector that fires on 100% of inputs is worse than no detector.

**Tampering is a correlation layer, not a detector.** A single forensic metric is noisy. Tampering
findings require independent detectors to agree on the same *area*, combine their confidences with a
noisy-OR damped by each source's reliability, and then name the region by intersecting it with the
extracted fields. That is how "Region: Total amount = $8,500.00 — potentially edited, confidence
81%" is produced: the region comes from measurement, the label from extraction.

**Comparison has pairing policies.** Two separate invoices in one claim legitimately carry different
totals and different invoice numbers; a dependant's date of birth legitimately differs from the
policyholder's. Comparing blindly manufactures findings, so each comparable field declares whether
it may be compared across any pair, only for the same person (with a strict, order-sensitive name
comparison — a shared surname is not identity), or only when the documents cite the same invoice.

**Verification grading distinguishes contradiction from detail.** A failed *critical* check (policy
not active, service date outside cover, document reported lost, write-off marker, amount disagrees)
is a **mismatch**: the record exists and does not support the document. A failed peripheral check is
a partial match.

## Frontend architecture

Server components fetch through `lib/api.ts`, which reads the httpOnly cookie server-side. Client
components call `/api/be/*`, a reverse proxy that attaches the token, streams the response, and
refreshes an expired access token once using the refresh cookie — so an investigator is never logged
out mid-review, and the browser bundle never holds a credential.

The **investigation workstation** is the centre of the product: the document stays on the left while
every panel on the right can draw a box around the pixels it is discussing. Selection state is
shared, so clicking a finding, a risk contributor or an extracted field all move the viewer to the
right page and highlight the right region.

Charts are client-only and use a **validated ordinal ramp** for risk bands rather than the
green/amber/red triad used on badges. That is deliberate: a green-to-red triad measures a CVD colour
difference of ΔE 4.2 between its endpoints (against a floor of 8), which would make the two most
important colours in the product indistinguishable for a common form of colour blindness. The
semantic triad is still used on badges, where the band's name is always present, so colour never
carries the meaning alone.
