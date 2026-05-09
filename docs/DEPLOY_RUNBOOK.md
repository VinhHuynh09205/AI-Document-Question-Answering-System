# Deployment Runbook

## 1. Preconditions

- Docker Engine and Docker Compose are installed.
- A valid `.env` file exists (copied from `.env.example`).
- Required values are set before production deploy:
  - `AUTH_SECRET_KEY`
  - `PG_PASSWORD`
  - `ADMIN_SETUP_SECRET` (required only when creating first admin via API)
- Optional provider keys depending on your deployment profile:
  - `OPENAI_API_KEY`
  - `GOOGLE_API_KEY`
  - `GROQ_API_KEY`
  - OAuth keys (`OAUTH_GOOGLE_*`, `OAUTH_GITHUB_*`)

## 2. Build and Start Stack

```bash
docker compose up --build -d
docker compose ps
```

Expected services:

- `aichatbox-api`
- `aichatbox-postgres`

Notes:

- `LOCAL_SEMANTIC_EMBEDDINGS=true` installs local semantic dependencies (larger image, slower build).
- `LOCAL_SEMANTIC_EMBEDDINGS=false` reduces build time and image size.

## 3. Basic Service Validation

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsS http://127.0.0.1:8000/api/v1/health/ready
curl -fsS http://127.0.0.1:8000/api/v1/metrics
```

Validate web routes:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/login`
- `http://127.0.0.1:8000/admin`

## 4. Run Smoke Test

Preferred (run inside API container):

```bash
docker compose exec aichatbox-api python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

Alternative (run from host venv):

```bash
python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

## 5. Bootstrap First Admin (One-Time)

Run only if no admin exists and `ADMIN_SETUP_SECRET` is configured.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/setup \
  -H "Content-Type: application/json" \
  -H "X-Admin-Setup-Secret: <your-admin-setup-secret>" \
  -d '{"username":"admin","password":"<strong-password>"}'
```

## 6. Backup Procedures

### 6.1 Vector backup

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ops/vector/backup
```

### 6.2 PostgreSQL backup

```bash
mkdir -p backups
docker exec aichatbox-postgres pg_dump -U aichatbox -d aichatbox > backups/pg_$(date +%Y%m%d_%H%M%S).sql
```

## 7. Restore Procedures

### 7.1 Restore latest vector backup

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ops/vector/restore-latest
```

### 7.2 Restore PostgreSQL from SQL dump

1. Stop API to avoid write traffic.

```bash
docker compose stop aichatbox-api
```

2. Recreate database and import dump.

```bash
docker exec -i aichatbox-postgres psql -U aichatbox -d postgres -c "DROP DATABASE IF EXISTS aichatbox;"
docker exec -i aichatbox-postgres psql -U aichatbox -d postgres -c "CREATE DATABASE aichatbox;"
cat backups/<dump-file>.sql | docker exec -i aichatbox-postgres psql -U aichatbox -d aichatbox
```

3. Start API and re-validate health.

```bash
docker compose start aichatbox-api
curl -fsS http://127.0.0.1:8000/api/v1/health
```

## 8. Rollback Procedure

1. Create backups before rollback (vector + PostgreSQL).
2. Checkout previous stable tag/commit.
3. Rebuild and restart stack:

```bash
docker compose up --build -d
```

4. If data incompatibility is detected, restore vector and/or PostgreSQL backup.
5. Run health checks and smoke test again.

## 9. Operational Checks After Deploy

- Monitor `GET /api/v1/metrics` for traffic, fallback count, and rate-limited requests.
- Check container health and logs:

```bash
docker compose ps
docker compose logs --tail=200 aichatbox-api
docker compose logs --tail=200 postgres
```

- Verify admin analytics endpoint is reachable:
  - `GET /api/v1/admin/analytics/usage` (admin token required)
- Verify workspace upload jobs and ask flow from UI/API.

## 10. Common Incident Commands

- Restart API only:

```bash
docker compose restart aichatbox-api
```

- Restart entire stack:

```bash
docker compose down
docker compose up -d
```

- Check vector store status:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/ops/vector/status
```

- Clear vector store (destructive):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ops/vector/clear
```

## 11. Incident Notes Template

- Time window:
- Affected endpoint(s):
- Symptoms:
- Mitigation:
- Root cause:
- Follow-up actions:
