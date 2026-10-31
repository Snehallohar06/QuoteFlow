# QuoteFlow — Deployment

Two routes: Docker Compose for a single host, or a manual deployment behind your
own process manager and reverse proxy.

---

## 1. Before anything else: the secrets

Two values must be set, and neither has a usable default. `docker-compose.yml`
uses the `${VAR:?message}` form, so the stack **refuses to start** rather than
falling back to a placeholder.

```bash
cp .env.docker.example .env

# Generate each one separately
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

| Variable | What it does | If you rotate it |
| --- | --- | --- |
| `JWT_SECRET_KEY` | Signs access and refresh tokens | Every signed-in user is signed out |
| `VERIFICATION_SECRET` | Keys the quotation integrity digests | **Every quotation already issued fails verification** — treat this as permanent for a deployment |

`.env` is git-ignored. A test (`test_an_env_template_carries_no_real_secrets`)
fails the build if a template ever ships a real key.

---

## 2. Docker Compose

```bash
cp .env.docker.example .env      # then set the two secrets
docker compose up --build -d
docker compose exec backend python -m app.db.seed --reset
```

The application is then on **<http://localhost:8080>**.

Optional demo data for the dashboards and approval queue:

```bash
docker compose exec backend python scripts/demo_activity.py \
  --base-url http://localhost:8000
```

### What the stack runs

| Service | Image | Published | Notes |
| --- | --- | --- | --- |
| `frontend` | nginx 1.27 serving the built bundle | `${HTTP_PORT:-8080}` → 80 | Proxies `/api` to the backend, so the browser is same-origin |
| `backend` | Python 3.12 slim, uvicorn, 2 workers | — | Runs as the unprivileged `quoteflow` user |
| `mongo` | MongoDB 8 | — | Health-gated; the backend waits for it |

Only the frontend publishes a port. The API and the database stay on the
compose network, so neither is reachable from outside the host.

### Volumes

| Volume | Holds | Why it matters |
| --- | --- | --- |
| `mongo-data` | The database | Obvious |
| `quotation-pdfs` | Rendered quotation PDFs | A quotation's PDF is regenerated on demand if missing, but keeping them avoids re-rendering and preserves the exact bytes that were delivered |

### Operating it

```bash
docker compose ps                        # health of each service
docker compose logs -f backend           # follow the API log
docker compose exec backend python scripts/test_report.py --quiet
docker compose down                      # stop, keeping the volumes
docker compose down -v                   # stop and delete the data
```

---

## 3. Manual deployment

### Backend

```bash
cd backend
python -m venv .venv && .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env     # then set the secrets and the Mongo URI
python -m app.db.seed    # omit --reset on an existing database

uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --workers 2 --proxy-headers --forwarded-allow-ips '*'
```

Production checklist:

- `APP_ENV=production` and `DEBUG=false`. Debug logging prints every database
  command, which is noisy and leaks query contents into logs.
- `--proxy-headers` with `--forwarded-allow-ips` set to your proxy, so the
  audit trail records the real client IP rather than the proxy's.
- Never `--reload`.
- Point `PDF_STORAGE_DIR` at persistent storage.
- Set `CORS_ORIGINS` only if the frontend is served from a different origin.
  Behind one reverse proxy it is unnecessary.

### Frontend

```bash
cd frontend
npm ci
npm run build          # outputs dist/
```

Serve `dist/` as static files. Two rules matter:

1. **Rewrite unknown paths to `index.html`** — it is a client-side router, so
   `/requests/abc123` must not 404.
2. **Never cache `index.html`**, and cache `/assets/*` hard. The asset
   filenames are content-hashed; a cached `index.html` points at asset URLs
   that no longer exist after a deploy.

`frontend/nginx.conf` is a working configuration for both. If the API is on
another origin, build with `VITE_API_BASE_URL=https://api.example.com`;
otherwise leave it blank and proxy `/api`.

---

## 4. MongoDB

Development uses a single local instance. For anything real:

| Concern | What to do |
| --- | --- |
| Authentication | Create a dedicated user with `readWrite` on the QuoteFlow database only, and put the credentials in `MONGODB_URI` |
| TLS | Use `mongodb+srv://` or add `?tls=true` |
| Indexes | Applied automatically at startup by `app/db/indexes.py`; no migration step |
| Backups | `mongodump` on a schedule. The quotation collection is the record of what was promised to customers |
| Replica set | Not required. See the limitation on transactions in [backend/README.md](backend/README.md#10-status) |

The connection is verified with a ping at startup; the app exits with a clear
message rather than starting half-alive.

---

## 5. Verifying a deployment

```bash
# Is it alive, and can it reach the database?
curl -fsS http://localhost:8080/health

# Does the API answer, and is it protected?
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/v1/customers   # expect 401

# Full suite inside the container
docker compose exec backend python -m pytest -q
docker compose exec backend python scripts/test_report.py --output TEST_REPORT.md
```

`/health` reports `{"status": "ok"}` only when MongoDB responds, so it is a
meaningful container health check rather than a liveness stub. Both images
declare a `HEALTHCHECK` that uses it.

---

## 6. What is not configured here

Stated plainly rather than implied:

- **No TLS termination.** Put this behind a proxy that terminates HTTPS
  (Caddy, Traefik, an ALB). The app sets `X-Forwarded-*`-aware options but does
  not hold certificates.
- **No rate limiting** on the login or public verification endpoints. Apply it
  at the proxy.
- **No horizontal scaling story.** Two uvicorn workers on one host is the
  tested configuration. Multiple backend replicas would work — the app keeps no
  in-process state — but it has not been tested that way.
- **No secrets manager integration.** Secrets come from the environment, which
  is what a secrets manager injects; nothing reads a vault directly.
- **No log shipping.** Logs go to stdout, which is what a container platform
  collects.
