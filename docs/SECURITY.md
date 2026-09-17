# Security and privacy

## What this system holds

Claim documents contain some of the most sensitive categories of personal data: medical treatment,
diagnoses, identity-document numbers, dates of birth, home addresses and bank details. The controls
below are designed around that, not bolted on.

## Threat model

| Threat | Control |
|---|---|
| Stolen session token | Token is httpOnly/SameSite and never in the browser bundle; short access TTL (45 min) with transparent refresh; every action attributed in the audit trail |
| Credential stuffing | Per-IP *and* per-account rate limits on sign-in; lockout after 6 failures; identical error wording for unknown account and wrong password |
| Privilege escalation via the UI | Authorisation is server-side on every endpoint; the UI's permission matrix is presentational only |
| Malicious upload (macro, JS, polyglot, executable) | Magic-byte sniffing before the declared type is trusted; static active-content scan; optional ClamAV; quarantine without deletion |
| Path traversal / storage escape | Storage keys are validated against a strict pattern and resolved paths are checked against the scope root |
| Document exfiltration by URL guessing | Nothing is public; signed links are HMAC-bound to resource + purpose + user with a 5-minute default TTL |
| Tampering with the evidence record | Originals are written read-only; findings carry the detector and model version; the audit trail is append-only and hash-chained |
| Insider rewriting history | `sha256(prev_hash ‖ canonical(entry))` chain; `/api/audit-logs/chain/verify` recomputes it and names the first divergence |
| Over-trusting the machine | Reasons are mandatory on adjudication; approval is refused while high findings are unadjudicated; every probabilistic signal ships with its uncertainty and its benign explanations |
| Data leakage through logs | Document bodies are never logged; the formatter redacts emails, long digit strings and card-like numbers; sensitive keys are dropped |
| Demo output mistaken for a real confirmation | `is_demo_data` on the result, `[EXTERNAL - DEMO]` in the report, a demo badge in the UI, and a disclaimer next to every answer |

## Authentication and authorisation

- Argon2id password hashing (bcrypt accepted for legacy verification), strength policy enforced at
  the schema level.
- JWT access and refresh tokens, typed (`type: access|refresh`) and issuer-checked, so an access
  token cannot be replayed as a refresh token.
- Four roles — Administrator, Fraud Investigator, Claims Officer, Reviewer — with **separation of
  duties by design**: the officer who decides a claim cannot adjudicate its findings, and the
  reviewer who adjudicates findings cannot decide the claim or escalate.

## Upload path

1. Stream with a hard ceiling; abort over `MAX_UPLOAD_MB`.
2. Sniff content type from magic bytes; reject anything outside PDF/JPEG/PNG/TIFF.
3. Validate the extension and record any disagreement with the declared type as a warning.
4. Parse structurally — a PDF that will not open, or an image that will not decode, is rejected as
   corrupt rather than stored.
5. Check page count and decoded resolution against limits.
6. SHA-256 the bytes; look for an existing document with the same hash.
7. Write once to `originals` at `0o440`, then create the document row.

## Privacy

- **Data minimisation** — extraction stores the fields the document schema declares, each with its
  provenance and confidence; the full OCR text is kept per page because an investigator needs to see
  what the machine read, and is never written to a log or an audit entry.
- **Audit redaction** — audit rows drop secrets and special-category fields before insertion. The
  claim record already holds the customer's details under normal access control and retention;
  duplicating them into an append-only store retained for years would widen exposure of the most
  sensitive fields for no accountability benefit.
- **Retention** — configurable per install. Derived artifacts are purged first; an original is only
  removed once the document has *also* been soft-deleted, so a scheduled job can never silently
  destroy evidence.
- **Access control** — every document read is audited (`document.viewed`), so a data-subject access
  request or an internal review can answer "who looked at this?" precisely.
- **Encryption** — TLS in transit at the proxy. At rest: enable `S3_SERVER_SIDE_ENCRYPTION` (SSE-S3
  or SSE-KMS) for object storage, and PostgreSQL disk or column encryption per your platform. The
  storage interface exposes no plaintext caching layer, so enabling SSE requires no code change.

## Reporting a vulnerability

This is an evaluation MVP. In a production deployment, route findings to your security team with the
affected endpoint, the role required, and the `x-request-id` from the response headers — every
request carries one and it appears in both the application log and the audit trail.
