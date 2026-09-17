# VeriDoc — Insurance Document Authenticity, Fraud Detection & Verification

A decision-support platform for insurance claim documents. It ingests medical bills, hospital
invoices, prescriptions, identity documents, claim forms, vehicle documents, repair estimates,
receipts, police reports and payment advices, then combines **forensic measurement, OCR and field
extraction, deterministic consistency rules, cross-document comparison, synthetic-media analysis and
trusted-source verification** into one explainable evidence record — and hands the decision to a
human investigator.

> **What this platform does not do.** It never concludes that a document is genuine or fraudulent.
> Findings carry a severity, a calibrated confidence, the evidence measured, and the detector and
> model version that produced them. The risk score is a **triage ranking** — Low Concern / Review
> Recommended / High Concern — not a probability that fraud occurred. A claim decision is always
> recorded against a named human, and the API refuses to approve a claim while high-severity
> findings remain unadjudicated.

---

## Contents

- [Quick start](#quick-start)
- [What it actually detects](#what-it-actually-detects)
- [Architecture](#architecture)
- [The analysis pipeline](#the-analysis-pipeline)
- [Running without Docker](#running-without-docker)
- [Demo environment](#demo-environment)
- [Testing](#testing)
- [API](#api)
- [Configuration](#configuration)
- [Security & privacy](#security--privacy)
- [Documentation map](#documentation-map)

---

## Quick start

Two commands, assuming Docker with Compose v2:

```bash
cp .env.example .env            # then edit JWT_SECRET at minimum
docker compose up -d --build
```

Then seed the demo environment (10 claims, 22 generated documents, full analysis):

```bash
docker compose exec api python -m app.db.seed --reset
```

| Service | URL | Notes |
|---|---|---|
| Investigator console | <http://localhost:3010> | Next.js UI |
| API + OpenAPI docs | <http://localhost:8088/docs> | FastAPI, Swagger UI |
| ReDoc | <http://localhost:8088/redoc> | |
| MinIO console | <http://localhost:9011> | `veridoc` / `veridoc-secret` |
| PostgreSQL | `localhost:55432` | `veridoc` / `veridoc` |
| Redis | `localhost:63799` | |

Sign in with any demo account — password **`Demo!2026`**:

| Account | Role | What it can do |
|---|---|---|
| `investigator@veridoc.example` | Fraud Investigator | Adjudicate findings, escalate, run verification, issue reports |
| `claims@veridoc.example` | Claims Officer | Create claims, upload, request information, record the claim decision |
| `reviewer@veridoc.example` | Reviewer | Second-line review of machine findings only |
| `admin@veridoc.example` | Administrator | Users, rules, providers, thresholds, audit |

Roles differ in what they may do, and the API enforces it — a Reviewer cannot escalate or decide, a
Claims Officer cannot adjudicate findings, and only an Administrator can retune rules.

---

## What it actually detects

Every signal below is a real measurement of the uploaded file. Nothing is simulated, and the
limitations are documented rather than hidden — see [`docs/DETECTION.md`](docs/DETECTION.md) for the
full catalogue including each detector's failure modes.

**Document structure & metadata (PDF)** — `/Info` and XMP metadata, creation vs modification
ordering, producing software classified by family (image editor, PDF manipulation tool, generator,
office suite, scanner), incremental revision generations, data after the final `%%EOF`, font
resources and embedding, embedded raster inventory, content annotations that draw over the page,
embedded JavaScript, attachments and open actions.

**Image forensics** — quantisation tables and estimated JPEG quality, error-level analysis read in
both directions, sensor-noise residual, ORB copy-move with offset clustering, JPEG-ghost compression
history, resampling periodicity, JPEG lattice energy. Region-level significance is established by a
**sliding-window two-sample test against the rest of the page**, computed over content blocks only —
per-block z-scores are not a usable instrument on a document that is mostly blank paper.

**Typography** — baseline alignment, glyph size, stroke weight from a distance transform, isolated
low-confidence recognition, and for digital PDFs the *exact* font each character was drawn with, so a
number set in a different font from its own line is detected exactly rather than statistically.

**OCR & extraction** — embedded PDF text layer where one exists (exact characters, exact
coordinates), Tesseract for scans and photographs, and a declarative per-document-type schema that
locates fields by label synonyms, column geometry and value patterns, with a bounding box for every
value so the UI can point at it.

**Consistency rules** — 20 deterministic rules: line-item sums, total arithmetic, tax against the
printed rate, payment reconciliation, date ordering and plausibility, cover windows, duplicate line
items, reference formats, currency ambiguity, VIN check digit (ISO 3779), IBAN mod-97, missing
required fields, and duplicate content by SHA-256 across claims.

**Cross-document comparison** — field-by-field across a claim bundle and against the claim record,
with type-aware comparison and *pairing policies* so unrelated documents are not compared: two
separate invoices are not expected to carry the same total, and a dependant's date of birth is not
expected to match the policyholder's.

**Synthetic-media analysis** — a provider interface with a deterministic, fully explainable demo
heuristic (eight measured features with published weights) and a production HTTP seam. The demo
provider is labelled as such everywhere its output appears.

**Trusted-source verification** — policy, provider accreditation, invoice, identity, vehicle and
settlement lookups behind one interface, with demo providers answering from a bundled sample
registry. Every result states its data source; demo answers can never be presented as real
confirmations.

---

## Architecture

```
┌──────────────────────┐        ┌────────────────────────────────────────────────┐
│  Next.js 15 console  │        │  FastAPI                                       │
│  (server components) │        │                                                │
│                      │        │  /api/documents   /api/claims   /api/reports   │
│  httpOnly cookie ────┼──────► │  /api/verification  /api/audit-logs  /api/...  │
│  /api/be/* proxy     │  JWT   │                                                │
└──────────────────────┘        │        ┌────────────────────────────────┐       │
                                │        │  analysis pipeline (14 stages) │       │
┌──────────────────────┐        │        └────────────────────────────────┘       │
│  RQ worker(s)        │◄───────┤  Redis queue (or in-process fallback)          │
│  same image as API   │        └────────────────────────────────────────────────┘
└──────────┬───────────┘                    │                     │
           │                                ▼                     ▼
           │                        ┌───────────────┐   ┌────────────────────────┐
           └───────────────────────►│  PostgreSQL   │   │  S3-compatible storage │
                                    │  25 tables    │   │  originals | artifacts │
                                    └───────────────┘   └────────────────────────┘
```

**Provider interfaces** (OCR, synthetic-media detection, verification, storage, malware scanning)
each have at least one local or demo implementation, so the product is complete and testable without
any external credentials — and a production provider drops in behind the same interface without
touching the pipeline.

**Storage is split in two.** `originals` holds the exact bytes the claimant uploaded, written
read-only and never modified; `artifacts` holds derived data (page renders, ELA maps, overlays,
generated reports) which can be regenerated and purged independently. That split is what makes
retention and secure deletion tractable without ever risking the evidence.

**The queue degrades gracefully.** With Redis reachable, uploads are analysed by an RQ worker. With
Redis down, the API falls back to a FastAPI background task and records which path executed on the
analysis run, so upload-and-analyse still works on a laptop with no Redis.

---

## The analysis pipeline

```
upload → validation → malware/security → render → OCR → classification → field extraction
       → metadata analysis → image & PDF forensics → synthetic-media analysis
       → tampering correlation → consistency rules → cross-document comparison
       → trusted-source verification → risk assessment → human review → decision
```

Two invariants govern the implementation:

1. **The original is never lost.** Every stage reads the stored original; nothing mutates or deletes
   it. A stage failure degrades that stage only — the run is marked `partial`, the degraded stage is
   named, and the risk assessment says plainly that its coverage was incomplete.
2. **Human decisions survive reprocessing.** Confirmed and dismissed findings are snapshotted before
   findings are regenerated and re-applied to the equivalent new finding, so re-running analysis
   never silently discards human judgement.

The console renders the pipeline as it actually ran — per stage: status, duration, provider, message
and finding count.

### How the risk score is produced

```
contribution(signal) = weight(code) × confidence × severity_multiplier
category_score       = cap × (1 − exp(−1.3 × Σ contributions / cap))
score                = round(100 × Σ category_scores / 72)
```

Weights, severities and thresholds live in the database and are editable by an administrator, so the
engine is configuration rather than code. Per-category ceilings stop a crowd of weak signals in one
category from outweighing a single decisive one elsewhere — while still allowing a genuinely
decisive category (an issuer contradicting the document) to reach High Concern on its own. Dismissed
findings are excluded; confirmed findings are treated as established. Every step is returned with
the score and printed in the report.

---

## Running without Docker

You need PostgreSQL 14+, and these system packages for the analysis pipeline:

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng poppler-utils libmagic1
# Redis is optional: without it the API analyses in-process
```

### Backend

```bash
cd backend
python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt

cp ../.env.example ../.env         # DATABASE_URL, JWT_SECRET, …
../.venv/bin/alembic upgrade head  # create the schema
../.venv/bin/python -m app.db.seed --reset   # demo data (optional)

../.venv/bin/uvicorn app.main:app --reload --port 8088
```

In a second terminal, the worker (only needed when `QUEUE_MODE=redis`):

```bash
cd backend && ../.venv/bin/python -m app.workers.worker
```

### Frontend

```bash
cd frontend
npm install
cat > .env.local <<'EOF'
BACKEND_API_URL=http://localhost:8088/api
NEXT_PUBLIC_DEMO_MODE=true
EOF
npm run dev          # http://localhost:3010
```

### Command reference

`make help` lists everything; the underlying commands are:

| Task | Command |
|---|---|
| Apply migrations | `alembic upgrade head` |
| Create a migration | `alembic revision --autogenerate -m "…"` |
| Check for model drift | `alembic check` |
| Seed reference data only | `python -m app.db.seed --reference-only` |
| Reset and seed everything | `python -m app.db.seed --reset` |
| Seed without analysis | `python -m app.db.seed --no-analysis` |
| Run the test suite | `pytest` |
| Run only fast tests | `pytest -m "not slow"` |
| Coverage | `pytest --cov=app --cov-report=term-missing` |
| Typecheck the frontend | `npm run typecheck` |
| Production build | `npm run build` |
| Purge expired artifacts (dry run) | `make purge-dry` |
| Exercise every requirement live | `make walkthrough` |

---

## Demo environment

`python -m app.db.seed --reset` builds a deterministic demo: **10 claims, 22 documents, 6 users,
99 detection rules, 17 provider configurations**, with scripted human-review history.

Demo documents are **generated, not bundled**: a specification describes each document and
`app/db/demo_documents.py` renders a real PDF or raster with the anomaly baked in at the object or
pixel level — a genuine incremental PDF revision, a value re-typed after capture, EXIF naming a
raster editor, a total set in a different font from its own line. The pipeline then has real
evidence to find, so the demo exercises the production code rather than fabricating findings. All
randomness is seeded, so the same seed yields byte-identical documents, identical findings and
identical scores on every machine.

The bundled scenarios, and where to see each one:

| Scenario | Claim | What to look at |
|---|---|---|
| 1 — Clean legitimate document | `CLM-2026-000101`, `CLM-2026-000106` | Everything reconciles; all checks pass; Low Concern |
| 2 — Edited invoice amount | `CLM-2026-000102` | Total in a different typeface, off its baseline, overlaid by an annotation; doesn't match its own line items |
| 3 — Metadata anomaly | `CLM-2026-000105` | `/Producer` is Photoshop, modified before created, incremental revision, trailing bytes |
| 4 — Cross-document mismatch | `CLM-2026-000102` | Invoice says 8,500.00; claim form and the claim record say 6,500.00 |
| 5 — Potential synthetic image | `CLM-2026-000108` | Smooth colour field, no sensor noise, no capture metadata → "Potential synthetic-media indicators" |
| 6 — Verification mismatch | `CLM-2026-000104`, `000109` | Lapsed policy outside its cover window, unaccredited clinic, returned payment, write-off marker, passport reported lost |
| Extra — Tampered photograph | `CLM-2026-000103` | Amounts block re-typed after capture: ELA, copy-move and a named tampering region |
| Extra — Duplicate re-upload | `CLM-2026-000110` | Byte-identical file already claimed under another case |
| Extra — Editor metadata on a photo | `CLM-2026-000110` | EXIF `Software` = Photoshop, re-saved 157 h after capture |
| Extra — Invalid VIN | `CLM-2026-000108` | ISO 3779 check digit fails; line items don't sum |

Suggested walkthrough: **Dashboard → Documents → open `DOC-2026-000004`** (the edited invoice).
Click any finding to box the exact pixels it refers to, then work through Extracted data →
Forensics → AIGC → Tampering → Consistency → Cross-document → Verification → Audit trail, dismiss a
finding with a reason, press *Recompute risk*, and generate the PDF report.

---

## Testing

```bash
cd backend && pytest                 # 174 tests
```

The suite runs against a real PostgreSQL database (`veridoc_test`, created automatically) and real
storage, because most of what is worth testing here — schema constraints, the audit hash chain, the
analysis pipeline end to end — is not meaningful against mocks. Only external providers are
substituted.

| File | Covers |
|---|---|
| `test_auth_rbac.py` | Sign-in, lockout wording, token types, the full permission matrix, per-endpoint authorisation |
| `test_upload_security.py` | Executables, extension spoofing, corrupt PDFs, oversized uploads, EICAR quarantine, hash integrity, duplicate detection |
| `test_extraction.py` | OCR routing, money/date/name normalisation, classification confidence, field extraction with boxes, label-in-heading regression |
| `test_rules_engine.py` | Every consistency rule in isolation, plus disable/severity/weight overrides and a deliberately broken rule |
| `test_crossdoc_verification.py` | Pairing policies, dependant handling, all six demo providers, outcome grading, unconfigured production provider |
| `test_risk_and_aigc.py` | Monotonicity, saturation, dismissed/confirmed handling, band thresholds, wording guarantees, AIGC determinism |
| `test_pipeline_e2e.py` | Clean and tampered documents end to end, provider outages, review carry-forward, artifact storage |
| `test_api_workflow.py` | The whole investigator workflow over HTTP, signed links, report generation, audit chain |
| `test_audit_and_admin.py` | Hash-chain integrity and tamper detection, PII redaction, rule/provider/threshold administration |
| `test_storage_and_errors.py` | Path traversal, bucket isolation, read-only originals, signed-URL binding, error contracts, security headers |

A scripted walkthrough of all twenty product requirements against a live instance is in
[`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md).

---

## API

Interactive documentation at `/docs`; the OpenAPI schema at `/openapi.json`.

```bash
# authenticate
TOKEN=$(curl -s localhost:8088/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"investigator@veridoc.example","password":"Demo!2026"}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# create a claim
curl -s localhost:8088/api/claims -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "customer_name": "Amelia R. Okonkwo",
  "policy_number": "POL-938472",
  "claim_type": "health",
  "claimed_amount": "8500.00",
  "incident_date": "2026-08-24"
}' | jq '{id, claim_number}'

# upload a document and analyse it
curl -s localhost:8088/api/documents -H "$AUTH" \
  -F file=@invoice.pdf -F claim_id=<CLAIM_ID> -F analyze=true | jq '.document.document_ref, .warnings'

# the full investigation payload
curl -s localhost:8088/api/documents/<DOC_ID> -H "$AUTH" \
  | jq '{risk: .risk_assessment.band, score: .risk_assessment.score,
         findings: [.findings[] | {code, severity, confidence, page}]}'

# adjudicate a finding (a reason is mandatory and enforced server-side)
curl -s localhost:8088/api/documents/<DOC_ID>/review -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "action": "dismiss_finding",
  "finding_id": "<FINDING_ID>",
  "reason": "Confirmed with the issuer that the printed total is correct."
}' | jq

# fold the decision into the score
curl -s -X POST localhost:8088/api/documents/<DOC_ID>/reassess -H "$AUTH" | jq '.risk.score, .risk.band'

# run trusted-source verification on demand
curl -s localhost:8088/api/verification/documents/<DOC_ID>/run -H "$AUTH" \
  -H 'Content-Type: application/json' -d '{"request_types":["policy_lookup","invoice_lookup"]}' \
  | jq '.results[] | {request_type, outcome: .result.outcome, demo: .result.is_demo_data}'

# generate and download a report
REPORT=$(curl -s localhost:8088/api/reports -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"document_id":"<DOC_ID>"}' | jq -r .id)
curl -s "localhost:8088/api/reports/$REPORT/export" -H "$AUTH" -o report.pdf

# verify the audit chain
curl -s localhost:8088/api/audit-logs/chain/verify -H "$AUTH" | jq '{intact, entries_total, head_hash}'
```

Full endpoint reference: [`docs/API.md`](docs/API.md).

---

## Configuration

Everything is environment-driven; see [`.env.example`](.env.example) for the annotated list. The
settings that change behaviour most:

| Variable | Default | Effect |
|---|---|---|
| `STORAGE_PROVIDER` | `local` | `local` filesystem or `s3` (MinIO, AWS S3, Supabase Storage, R2) |
| `QUEUE_MODE` | `redis` | `redis` uses RQ workers; `inline` analyses in-process with no worker |
| `OCR_PROVIDER` | `hybrid` | `hybrid` \| `tesseract` \| `pdf_text` \| `demo_fixture` |
| `AIGC_PROVIDER` | `demo_heuristic` | `demo_heuristic` \| `remote_http` (needs `AIGC_REMOTE_URL`/`_API_KEY`) |
| `VERIFICATION_PROVIDER` | `demo` | `demo` \| `remote_http` (needs `VERIFICATION_REMOTE_URL`/`_API_KEY`) |
| `MALWARE_SCANNER` | `heuristic` | `heuristic` static checks, or `clamav` against a clamd service |
| `MAX_UPLOAD_MB` | `25` | Hard ceiling, enforced while streaming |
| `RETENTION_DAYS` | `365` | Feeds the retention job; artifacts are purged before originals |
| `SIGNED_URL_TTL_SECONDS` | `300` | Lifetime of a signed document link |

The active OCR, synthetic-media and verification providers can also be switched at runtime from
**Integrations** in the console; the database setting overrides the environment default.

---

## Security & privacy

- **Authentication** — JWT access/refresh tokens, Argon2id password hashing, lockout after repeated
  failures, identical error wording for unknown accounts and wrong passwords.
- **Authorisation** — a four-role permission matrix enforced on **every** endpoint server-side. The
  UI uses the same matrix only to hide controls.
- **No token in the browser** — the console stores the access token in an httpOnly, SameSite=Lax
  cookie and proxies API calls server-side, so page scripts cannot read or exfiltrate it. Expired
  access tokens are refreshed transparently mid-review.
- **Upload validation** — content-type sniffed from magic bytes before the declared type or the
  filename is trusted; extension, size, page count, decodability and polyglot checks; filenames
  sanitised and never used as storage keys.
- **Malware handling** — a `suspicious` or `infected` verdict quarantines the document *without
  deleting it*: the evidence stays downloadable and the security finding is recorded.
- **Document access** — nothing is public. Bytes are served either to an authenticated session or
  via a short-lived HMAC-signed link bound to the resource, the purpose and the user, with
  `Cache-Control: private, no-store`.
- **Audit trail** — append-only with a SHA-256 hash chain (`entry_hash = sha256(prev_hash ‖
  canonical(entry))`). `/api/audit-logs/chain/verify` recomputes it and names the first divergence.
- **PII discipline** — document bodies are never logged. Audit entries store structured field diffs
  with secrets and special-category fields (patient name, date of birth, national ID, address,
  diagnosis, account number) redacted before the row is written; the log records *who did what*, not
  the contents of a medical document.
- **Transport & headers** — CSP, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, a permissions
  policy, HSTS in production, per-IP and per-endpoint rate limiting, CORS restricted to configured
  origins.
- **Secrets** — read from the environment only. Provider records store the *names* of the variables
  a provider needs, never their values.

See [`docs/SECURITY.md`](docs/SECURITY.md) for the threat model and the encryption-at-rest options.

---

## Documentation map

| Document | Contents |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Module layout, data model, pipeline internals, the design decisions and why they were made |
| [`docs/DETECTION.md`](docs/DETECTION.md) | Every detector: what it measures, what it cannot tell you, and its benign explanations |
| [`docs/API.md`](docs/API.md) | Endpoint reference with request/response examples |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Production deployment, scaling, backups, Supabase notes |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model, controls, privacy and retention |
| [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) | The twenty product requirements, demonstrated against a live instance |

## Licence

Proprietary — supplied as an evaluation MVP.
