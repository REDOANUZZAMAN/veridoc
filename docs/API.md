# API reference

Base path `/api`. Interactive documentation at `/docs`, schema at `/openapi.json`.

All responses are JSON except document bytes, page renders and report PDFs. Errors are uniform:

```json
{ "error": { "code": "validation_failed", "message": "…", "details": [], "retryable": false } }
```

| Code | Status | Meaning |
|---|---|---|
| `not_authenticated` | 401 | Missing, invalid or expired token |
| `permission_denied` | 403 | The role lacks the permission the endpoint declares |
| `not_found` | 404 | No such resource |
| `conflict` | 409 | Conflicts with current state (e.g. approving with unadjudicated findings) |
| `validation_failed` | 422 | Request or business-rule validation |
| `unsupported_document` | 415 | Not a PDF/JPG/PNG/TIFF |
| `corrupt_document` | 400 | Unparseable or truncated |
| `file_too_large` | 413 | Over `MAX_UPLOAD_MB` |
| `rate_limited` | 429 | Retryable |
| `provider_unavailable` | 503 | OCR / detection / verification dependency down; retryable |
| `database_unavailable` | 503 | Nothing was modified; retryable |

---

## Authentication

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/auth/login` | — | Rate limited per IP *and* per account |
| POST | `/auth/refresh` | — | Refresh token only; an access token is rejected |
| POST | `/auth/logout` | session | Records the sign-out in the audit trail |
| GET | `/auth/me` | session | Returns the effective permission list |
| POST | `/auth/change-password` | session | Enforces the strength policy |
| GET | `/auth/roles` | session | Role catalogue with permissions |

```bash
curl -s localhost:8088/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"investigator@veridoc.example","password":"Demo!2026"}'
```

```json
{
  "access_token": "eyJ…", "refresh_token": "eyJ…", "token_type": "bearer",
  "expires_at": "2026-09-17T17:25:00Z",
  "user": { "email": "investigator@veridoc.example", "role_name": "fraud_investigator",
            "role_label": "Fraud Investigator", "permissions": ["audit:read", "claim:read", "…"] }
}
```

## Documents

| Method | Path | Permission |
|---|---|---|
| POST | `/documents` | `document:upload` |
| GET | `/documents` | `document:read` |
| GET | `/documents/{id}` | `document:read` |
| GET | `/documents/{id}/findings` | `document:read` |
| GET | `/documents/{id}/analysis` | `document:read` |
| POST | `/documents/{id}/analyze` | `document:analyze` |
| POST | `/documents/{id}/reassess` | `document:analyze` |
| POST | `/documents/{id}/classification` | `document:analyze` |
| POST | `/documents/{id}/review` | per action (see below) |
| POST | `/documents/{id}/links` | `document:download` |
| GET | `/documents/{id}/file` | `document:download` or a signed link |
| GET | `/documents/{id}/pages/{n}/render` | `document:download` or a signed link |
| DELETE | `/documents/{id}?reason=…` | `document:delete` (soft delete) |

**Upload** — `multipart/form-data`: `file` (required), `claim_id`, `source`, `analyze`.

```bash
curl -s localhost:8088/api/documents -H "$AUTH" \
  -F file=@invoice.pdf -F claim_id=$CLAIM -F source=portal_upload -F analyze=true
```

```json
{
  "document": { "document_ref": "DOC-2026-000023", "sha256": "1fcd…", "page_count": 1,
                "processing_status": "queued", "mime_type": "application/pdf" },
  "analysis": { "queued": true, "analysis_run_id": "…", "mode": "redis", "job_id": "…" },
  "warnings": ["An identical file (SHA-256 match) is already on record as DOC-2026-000001 …"],
  "message": "DOC-2026-000023 stored successfully. The original file is preserved unchanged. Analysis is under way."
}
```

Content type is sniffed from magic bytes *before* the declared type or the filename is trusted;
`warnings` surfaces disagreements without rejecting a document that is otherwise valid.

**List** — `page`, `page_size`, `claim_id`, `status`, `risk_band`, `document_type`,
`verification_state`, `search` (reference, filename or SHA-256), `sort`, `order`.

**Detail** — one payload for the whole investigation: pages, OCR (with word boxes), extracted fields
and line items, metadata entries, all findings, risk assessment, latest analysis run with its stage
timeline, verification requests, review actions, and the schema for the detected document type.

**Review** — `action` is one of `confirm_finding`, `dismiss_finding`, `request_information`,
`mark_document_verified`, `reject_document`, `escalate_investigation`. All except
`request_information` require a written `reason` of at least 10 characters, enforced server-side.
Permissions map per action: `finding:confirm`, `finding:dismiss`, `finding:request_info`,
`document:verify`, `investigation:escalate`.

```bash
curl -s localhost:8088/api/documents/$DOC/review -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "action": "confirm_finding", "finding_id": "'$FINDING'",
  "reason": "Confirmed with the issuer that the printed total is 6,500.00."
}'
```

**Signed links** — `POST /documents/{id}/links` mints short-lived HMAC-signed relative URLs for the
original and each page render, bound to the resource, the purpose and the requesting user:

```json
[ { "url": "/api/documents/…/file?exp=1789…&nonce=…&sig=…&uid=…",
    "expires_at": "2026-09-17T17:05:00Z", "purpose": "original",
    "note": "Short-lived signed link bound to your user account. …" } ]
```

**Page renders** — `?layer=page` (default), `thumbnail`, or a forensic layer such as `ela` when one
was produced for that page. Requesting an unavailable layer returns 404 listing what *is* available.

## Claims

| Method | Path | Permission |
|---|---|---|
| POST | `/claims` | `claim:create` |
| GET | `/claims` | `claim:read` |
| GET | `/claims/{id}` | `claim:read` (accepts id or claim number) |
| PATCH | `/claims/{id}` | `claim:update` (+ `investigation:assign` to reassign) |
| POST | `/claims/{id}/decision` | `claim:decide` |

Claim detail includes the documents, verification history, a findings summary, investigations, the
full cross-document comparison matrix, and a merged timeline.

**Decision** — `decision` is `approve` \| `decline` \| `refer` \| `withdraw`, with a reason of at
least 12 characters. **Approval returns 409 while any high or critical finding across the claim is
unadjudicated** — machine findings must not become a decision by default.

## Verification

| Method | Path | Permission |
|---|---|---|
| GET | `/verification/providers` | `verification:read` |
| GET | `/verification/requests` | `verification:read` |
| POST | `/verification/documents/{id}/run` | `verification:run` |

```bash
curl -s localhost:8088/api/verification/documents/$DOC/run -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"request_types":["policy_lookup","invoice_lookup"],"overrides":{"policy_number":"POL-938472"}}'
```

Each result carries `provider_mode`, `is_demo_provider`, the individual checks with expected vs
actual, `is_demo_data` and `data_source_disclaimer`. Request types: `policy_lookup`,
`provider_lookup`, `invoice_lookup`, `identity_lookup`, `vehicle_lookup`, `payment_lookup`.

## Investigations

| Method | Path | Permission |
|---|---|---|
| GET | `/investigations` | `investigation:read` (`?mine=true`, `status`, `priority`) |
| POST | `/investigations` | `investigation:escalate` |
| GET | `/investigations/{id}` | `investigation:read` (id or case number) |
| PATCH | `/investigations/{id}` | `investigation:note` (+ `investigation:close` to close) |
| POST | `/investigations/{id}/notes` | `investigation:note` |

Closing a case requires a resolution and a reason.

## Reports

| Method | Path | Permission |
|---|---|---|
| POST | `/reports` | `report:generate` |
| GET | `/reports` | `report:read` |
| GET | `/reports/{id}` | `report:read` |
| GET | `/reports/{id}/export` | `report:read` (PDF; `?disposition=inline`) |

The report records its own SHA-256, the document's SHA-256, the pipeline and rules versions, and the
audit-chain state at generation. Findings are tagged by provenance — `[MEASURED]`, `[RULE]`,
`[MODEL]`, `[EXTERNAL]`, `[HUMAN]` — and demo verification results are marked `[EXTERNAL - DEMO]`.

## Audit

| Method | Path | Permission |
|---|---|---|
| GET | `/audit-logs` | `audit:read` (`action`, `resource_type`, `resource_id`, `actor_id`, `since`, `until`, `search`) |
| GET | `/audit-logs/actions` | `audit:read` |
| GET | `/audit-logs/chain/verify` | `audit:read` |

```json
{ "entries_checked": 249, "entries_total": 249, "intact": true,
  "head_hash": "7c0b…", "broken_at": null,
  "algorithm": "sha256(prev_hash || canonical_json(entry))" }
```

## Administration

| Method | Path | Permission |
|---|---|---|
| GET | `/rules`, `/rules/catalogue` | `rule:read` |
| PATCH | `/rules/{code}` | `rule:write` (`enabled`, `default_severity`, `weight`, `params`) |
| GET | `/providers`, `/providers/runtime` | `provider:read` |
| PATCH | `/providers/{kind}/{key}` | `provider:write` (activating one deactivates the rest of that kind) |
| GET | `/settings` | `settings:read` |
| PUT | `/settings/{key}` | `settings:write` (`risk_thresholds` is validated) |
| GET | `/users`, `/users/{id}`, `/users/investigators`, `/users/workload` | `user:read` / `claim:read` |
| POST | `/users` | `user:write` |
| PATCH | `/users/{id}` | `user:write` |

## Dashboard and system

| Method | Path | Permission |
|---|---|---|
| GET | `/dashboard?days=21` | `dashboard:read` |
| GET | `/health` | — |
| GET | `/ready` | — (database, storage and queue status) |
| GET | `/system/capabilities` | — (limits, providers, versions, privacy settings) |
