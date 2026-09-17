# Deployment

## Topology

```
              ┌──────────────┐
  TLS ───────►│ reverse proxy│  (Traefik / nginx / ALB)
              └──┬────────┬──┘
                 │        │
        ┌────────▼──┐  ┌──▼─────────────┐
        │  web × N  │  │   api × N      │  stateless, horizontally scalable
        └───────────┘  └──┬──────────┬──┘
                          │          │
                 ┌────────▼───┐  ┌───▼──────┐
                 │ PostgreSQL │  │  Redis   │
                 └────────────┘  └───┬──────┘
                                     │
                              ┌──────▼──────┐
                              │ worker × N  │  same image as api
                              └──────┬──────┘
                                     │
                            ┌────────▼─────────┐
                            │ object storage   │  originals | artifacts
                            └──────────────────┘
```

Both application tiers are stateless. Scale the API for request volume and the workers for analysis
throughput — a page of analysis costs roughly 3–5 seconds of CPU, dominated by rasterisation and the
pixel metrics.

## Before going to production

1. **Generate a real JWT secret.** `openssl rand -hex 48`. Rotating it invalidates all sessions.
2. **Set `APP_ENV=production`** — enables HSTS and turns off debug behaviour.
3. **Set `DEMO_MODE=false` and `NEXT_PUBLIC_DEMO_MODE=false`** so the demo banner and the sign-in
   page's demo accounts disappear.
4. **Never seed demo data.** `scripts/entrypoint.sh` only seeds when `SEED_ON_START=true`, which
   should never be set in production. Create the first administrator with
   `python -m app.db.seed --reference-only` and then rotate its password immediately.
5. **Switch storage to S3** (`STORAGE_PROVIDER=s3`) with private buckets, bucket versioning on
   `originals`, and object-lock or a bucket policy that denies deletes if evidence must be immutable.
   Set `S3_SERVER_SIDE_ENCRYPTION=AES256` (or `aws:kms` with a CMK).
6. **Restrict CORS and hosts** — `ALLOWED_ORIGINS` to the console origin only, `TRUSTED_HOSTS` to
   your hostnames.
7. **Terminate TLS at the proxy** and pass `X-Forwarded-For`; the API reads it for audit and rate
   limiting (it is started with `--proxy-headers --forwarded-allow-ips`).
8. **Configure real providers** if you need them: `AIGC_PROVIDER=remote_http`,
   `VERIFICATION_PROVIDER=remote_http`, `MALWARE_SCANNER=clamav`. Until then the platform runs on
   local/demo implementations and says so on screen and in every report.
9. **Review the retention settings** under Settings and schedule the purge job.

## Migrations

```bash
alembic upgrade head        # apply (the container entrypoint does this on start)
alembic check               # fail CI if the models have drifted from the migrations
alembic revision --autogenerate -m "add x"
alembic downgrade -1
```

Migrations take the URL from `DATABASE_URL` via the application settings, so they cannot be pointed
at the wrong database by a stale ini file.

## Supabase / managed PostgreSQL

The schema is plain PostgreSQL with `JSONB` and an identity column; no extensions are required.

```
DATABASE_URL=postgresql+psycopg://postgres:<password>@db.<ref>.supabase.co:5432/postgres
```

Use the **session pooler** (port 5432) rather than the transaction pooler: the audit chain takes a
`pg_advisory_xact_lock` to serialise appends, and advisory locks need session affinity. With the
transaction pooler, set `DB_POOL_SIZE=1` and `?options=-c%20statement_timeout%3D0`, or keep a direct
connection for the workers.

Supabase Storage is S3-compatible:

```
STORAGE_PROVIDER=s3
S3_ENDPOINT_URL=https://<ref>.supabase.co/storage/v1/s3
S3_ACCESS_KEY_ID=…
S3_SECRET_ACCESS_KEY=…
```

## Health and monitoring

| Endpoint | Use |
|---|---|
| `/api/health` | Liveness — process is up |
| `/api/ready` | Readiness — database, storage and queue reachable, with versions |
| `/api/system/capabilities` | Configuration audit: active providers, limits, retention |

Worth alerting on: `documents.processing_status = failed` (analysis failures), RQ failed-job registry
depth, `/api/audit-logs/chain/verify` returning `intact: false` (should be impossible — investigate
the database directly), and storage write failures in the API log (`s3_unavailable_falling_back_to_local`).

Logs are structured, single-line, and PII-redacting: emails, long digit strings and card-like numbers
are masked, and sensitive keys are dropped entirely by the formatter.

## Backup and recovery

Three things must be backed up together, or a restore will produce findings that reference documents
that no longer exist:

1. **PostgreSQL** — findings, audit chain, review decisions. `pg_dump` or PITR.
2. **`originals`** — the evidence. Versioned bucket; treat as write-once.
3. **`artifacts`** — page renders, forensic layers, report PDFs. Recoverable by re-running analysis,
   but reports are cheaper to keep than to re-justify.

To validate a restore: `GET /api/audit-logs/chain/verify` must return `intact: true`, and
re-analysing a sample document must reproduce its recorded findings — the pipeline is deterministic
for a given pipeline and rules version.

## Performance notes

- `PIXEL_ANALYSIS_PAGE_LIMIT` (12) and `OCR_PAGE_LIMIT` (30) bound the work a single document can
  demand. A 60-page PDF is rendered and OCR'd but only the first 12 pages get the pixel suite.
- The JPEG-ghost map re-encodes the page at eight qualities; it runs only for JPEG sources, where it
  is informative.
- Analysis is CPU-bound and single-threaded per document — scale out with workers rather than up.
- Page renders are cached in the artifacts bucket, so the viewer never re-rasterises.
