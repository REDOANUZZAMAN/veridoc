# Deploying on dokploy

**Yes — there are Dockerfiles; no nixpacks needed.**

| Path | Builds | Notes |
|---|---|---|
| `backend/Dockerfile` | API **and** worker | One image, two roles — the compose file overrides the command |
| `frontend/Dockerfile` | Console | Multi-stage, Next.js `standalone` output, runs as UID 10001 |
| `docker-compose.dokploy.yml` | The whole stack | Traefik labels for this host, no published ports |

> **Do not use nixpacks for the backend.** The analysis pipeline needs system packages that a
> buildpack will not install: `tesseract-ocr` (pixel OCR), `poppler-utils` (PDF rasterisation),
> `libmagic1` (content-type sniffing) and `libgl1`/`libglib2.0-0` (OpenCV runtime). Without them the
> render and OCR stages fail at runtime, which the Dockerfile exists to prevent.

---

## Before you start: two things about this host

1. **DNS does not exist yet.** `rmaikr.top` is on Cloudflare with a record per subdomain — there is
   no wildcard — so `veridoc.rmaikr.top` currently does not resolve. Add it first:

   Cloudflare → `rmaikr.top` → DNS → **Add record**
   `A` · name `veridoc` · content `62.146.233.41` · proxy **on** (orange), matching your other
   subdomains.

   If the certificate fails to issue, grey-cloud the record until Traefik has completed the
   HTTP-01 challenge, then turn the proxy back on. With the proxy on, keep SSL/TLS mode at
   **Full**.

2. **Ports 9000/9001 are already in use** on this box, and 8088/3010 are the dev ports. The dokploy
   compose file publishes **nothing** — Traefik reaches the console over `dokploy-network`, exactly
   how your chatwoot and mautic stacks work. Nothing to reassign.

---

## Option A — dokploy Compose app (recommended)

This stack is five services, so it wants the **Compose** type rather than the Application type.

1. dokploy → **Projects** → *Create project* → name it `veridoc`.
2. Inside the project → **Create Service** → **Compose**.
3. **Provider**: GitHub → repository `REDOANUZZAMAN/veridoc` → branch `main`.
   (If the repo is not listed, re-run the GitHub App authorisation so it can see private repos.)
4. **Compose path**: `docker-compose.dokploy.yml`
5. **Environment** — paste this, with your own generated secrets:

   ```env
   APP_DOMAIN=veridoc.rmaikr.top
   JWT_SECRET=<openssl rand -hex 48>
   POSTGRES_PASSWORD=<openssl rand -hex 24>

   # Optional
   APP_NAME=VeriDoc
   MAX_UPLOAD_MB=25
   RETENTION_DAYS=365
   # PyPI is ~15 kB/s from this host; a mirror makes the build minutes instead of an hour
   PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
   PIP_TRUSTED_HOST=mirrors.aliyun.com
   ```

   **Never set `SEED_ON_START`.** The entrypoint only seeds when it is `true`, and it would load
   ten demo claims into your production database.

6. **Domains**: the compose file already carries its own Traefik labels, so you do not need to add a
   domain in the dokploy UI. If you prefer dokploy to manage it, point the domain at the `web`
   service on port `3000` and delete the `labels:` block from that service so the two do not fight.
7. **Deploy**. The first build takes a while — the API image installs tesseract, poppler and OpenCV.
8. Turn on **Auto Deploy** so `git push` redeploys, which is the workflow the rest of your stacks use.

### First run

The entrypoint waits for PostgreSQL and runs `alembic upgrade head`, so the schema is created
automatically. Then create your administrator:

```bash
docker compose -p veridoc exec api python -m app.db.seed --reference-only
```

That seeds roles, the 99 detection rules, provider configurations and settings, plus the six demo
accounts. **Immediately** sign in as `admin@veridoc.example` / `Demo!2026`, create your real
administrator under *Users*, and then disable or delete the demo accounts — they are public
knowledge, they are in the README.

---

## Option B — separate dokploy Applications

If you would rather have dokploy manage each piece, it is three applications plus two databases:

| dokploy object | Type | Settings |
|---|---|---|
| `veridoc-db` | Database → PostgreSQL 16 | Note the internal connection string |
| `veridoc-redis` | Database → Redis 7 | |
| `veridoc-api` | Application → Dockerfile | Build path `backend/`, port `8000`, no public domain needed |
| `veridoc-worker` | Application → Dockerfile | Build path `backend/`, command `python -m app.workers.worker` |
| `veridoc-web` | Application → Dockerfile | Build path `frontend/`, port `3000`, domain `veridoc.rmaikr.top` |

Two things to get right:

- **`veridoc-api` and `veridoc-worker` must share the storage volume.** Mount the same dokploy
  volume at `/var/veridoc/storage` on both, or the worker will write page renders the API cannot
  read. (Option A handles this with a named volume.)
- **`veridoc-web` needs `BACKEND_API_URL=http://veridoc-api:8000/api`** — the internal service
  name. The console calls the API server-side only; if you point it at a public URL you lose the
  reason the token never reaches the browser.

---

## After deploying

| Check | Expected |
|---|---|
| `https://veridoc.rmaikr.top/login` | The sign-in page, with a valid certificate |
| `docker compose -p veridoc exec api curl -s localhost:8000/api/ready` | `ready: true`, database/storage/queue healthy, `workers: 1` |
| Upload a document | Status moves `queued → analysed`. If it stays `queued`, the worker is not running |
| `docker compose -p veridoc logs -f worker` | `Listening on veridoc-analysis...` |

### Production checklist

- [ ] `JWT_SECRET` is 48+ random bytes and not the one from `.env.example` (rotating it signs
      everyone out)
- [ ] Demo accounts disabled; a real administrator created
- [ ] `DEMO_MODE=false` (set by the compose file) — removes the demo banner and the sign-in hints
- [ ] Back up **together**: the database, the `storage-data` volume (originals are the evidence) and
      your env values. A database restored without its originals produces findings that reference
      documents that no longer exist
- [ ] Decide on real providers: `AIGC_PROVIDER=remote_http`, `VERIFICATION_PROVIDER=remote_http`,
      `MALWARE_SCANNER=clamav`. Until then the platform runs on demo/local implementations and says
      so on screen and in every report
- [ ] Consider moving storage to S3/MinIO (`STORAGE_PROVIDER=s3`) with a versioned `originals`
      bucket, so evidence survives a host loss

### Cloudflare notes

The console works fine behind the orange cloud. Two limits worth knowing: Cloudflare caps request
bodies at 100 MB on the free plan (the app's own limit is 25 MB, so it is not the binding
constraint), and it buffers uploads — a slow large upload shows progress in the browser before
Traefik sees it.

---

## Deploying by hand instead (matching `/root/stacks/*`)

Your existing stacks are hand-managed compose files. If you prefer that for this one:

```bash
git clone git@github.com:REDOANUZZAMAN/veridoc.git /root/stacks/veridoc
cd /root/stacks/veridoc
cat > .env <<'ENV'
APP_DOMAIN=veridoc.rmaikr.top
JWT_SECRET=<openssl rand -hex 48>
POSTGRES_PASSWORD=<openssl rand -hex 24>
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
PIP_TRUSTED_HOST=mirrors.aliyun.com
ENV
chmod 600 .env
docker compose -f docker-compose.dokploy.yml up -d --build
docker compose -f docker-compose.dokploy.yml exec api python -m app.db.seed --reference-only
```

Updating later is `git pull && docker compose -f docker-compose.dokploy.yml up -d --build`.
