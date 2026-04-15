# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-04-07

### Added
- Clean architecture project layout with SOLID-oriented interfaces and dependency injection.
- Document ingestion pipeline for PDF, DOCX, TXT, MD, CSV.
- Chunking service and persistent FAISS vector storage.
- Grounded ask pipeline with strict fallback rule when context is insufficient.
- Optional authentication endpoints for register and login.
- Operational endpoints for health, readiness, metrics, vector backup, and vector restore.
- Request tracing with X-Request-ID and structured runtime metrics.
- In-memory rate limiting for ask and upload endpoints.
- Docker packaging, docker-compose setup, and CI workflow.
- Benchmark utility and release smoke test utility.

### Changed
- Ask flow now uses retrieval + relevance filtering guardrails before answer generation.
- Security hardening with CORS configuration and HTTP security headers.
- Graceful shutdown persistence moved to FastAPI lifespan event.

### Notes
- Local container vulnerability scanner warnings are accepted for current base image choice.
- Production deployments should use a hardened base image from internal security policy.
