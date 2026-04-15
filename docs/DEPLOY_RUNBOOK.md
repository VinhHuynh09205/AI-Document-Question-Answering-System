# Deployment Runbook

## 1. Preconditions
- Docker and Docker Compose are installed.
- A valid `.env` file exists (copied from `.env.example`).
- Required secrets are set:
  - `OPENAI_API_KEY`
  - `AUTH_SECRET_KEY`

## 2. Build and Start
```bash
docker compose up --build -d
```

## 3. Validate Service
```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/health/ready
curl http://127.0.0.1:8000/api/v1/metrics
```

## 4. Run Smoke Test
```bash
python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

## 5. Backup Vector Store
```bash
curl -X POST http://127.0.0.1:8000/api/v1/ops/vector/backup
```

## 6. Restore Latest Vector Backup
```bash
curl -X POST http://127.0.0.1:8000/api/v1/ops/vector/restore-latest
```

## 7. Rollback Procedure
1. Stop current deployment:
```bash
docker compose down
```
2. Revert to previous image tag or previous commit.
3. Start the stack again:
```bash
docker compose up -d
```
4. Restore latest vector backup if required.

## 8. Operational Checks
- Monitor `GET /api/v1/metrics` for request volume and throttling.
- Check logs for frequent fallback answers and rate-limited responses.
- Verify `X-Request-ID` is present in responses for traceability.

## 9. Incident Notes Template
- Time window:
- Affected endpoint(s):
- Symptoms:
- Mitigation:
- Root cause:
- Follow-up actions:
