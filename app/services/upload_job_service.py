from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4

from app.services.interfaces.upload_job_service import IUploadJobService


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clamp_progress(value: int) -> int:
    return max(0, min(100, value))


@dataclass(slots=True)
class _UploadJob:
    job_id: str
    username: str
    chat_id: str
    status: str
    stage: str
    progress: int
    files_total: int
    files_processed: int
    chunks_total: int
    chunks_indexed: int
    original_names: list[str] = field(default_factory=list)
    message: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "chat_id": self.chat_id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "files_total": self.files_total,
            "files_processed": self.files_processed,
            "chunks_total": self.chunks_total,
            "chunks_indexed": self.chunks_indexed,
            "original_names": list(self.original_names),
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class InMemoryUploadJobService(IUploadJobService):
    def __init__(self, retention_seconds: int = 3600) -> None:
        self._retention_seconds = max(60, retention_seconds)
        self._jobs: dict[str, _UploadJob] = {}
        self._lock = Lock()

    def create_job(self, username: str, chat_id: str, original_names: Sequence[str]) -> dict[str, Any]:
        with self._lock:
            self._purge_expired_locked()
            job = _UploadJob(
                job_id=str(uuid4()),
                username=username,
                chat_id=chat_id,
                status="queued",
                stage="queued",
                progress=0,
                files_total=len(original_names),
                files_processed=0,
                chunks_total=0,
                chunks_indexed=0,
                original_names=list(original_names),
                message="Đã nhận file, đang chờ xử lý",
            )
            self._jobs[job.job_id] = job
            return job.snapshot()

    def mark_processing(self, job_id: str, message: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = "processing"
            job.stage = "processing"
            if message:
                job.message = message
            job.updated_at = _utc_now_iso()
            return job.snapshot()

    def update_progress(
        self,
        job_id: str,
        *,
        stage: str | None = None,
        progress: int | None = None,
        files_processed: int | None = None,
        chunks_total: int | None = None,
        chunks_indexed: int | None = None,
        message: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if stage is not None:
                job.stage = stage
            if progress is not None:
                job.progress = _clamp_progress(progress)
            if files_processed is not None:
                job.files_processed = max(0, min(files_processed, job.files_total))
            if chunks_total is not None:
                job.chunks_total = max(0, chunks_total)
            if chunks_indexed is not None:
                job.chunks_indexed = max(0, chunks_indexed)
            if message is not None:
                job.message = message
            job.updated_at = _utc_now_iso()
            return job.snapshot()

    def mark_completed(
        self,
        job_id: str,
        *,
        files_processed: int,
        chunks_indexed: int,
        message: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = "completed"
            job.stage = "completed"
            job.progress = 100
            job.files_processed = max(0, min(files_processed, job.files_total))
            job.chunks_indexed = max(chunks_indexed, 0)
            if job.chunks_total < job.chunks_indexed:
                job.chunks_total = job.chunks_indexed
            job.message = message
            job.error = None
            job.updated_at = _utc_now_iso()
            return job.snapshot()

    def mark_failed(self, job_id: str, error: str, message: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = "failed"
            job.stage = "failed"
            if job.progress < 100:
                job.progress = max(job.progress, 1)
            job.error = error
            if message is not None:
                job.message = message
            job.updated_at = _utc_now_iso()
            return job.snapshot()

    def get_job(self, job_id: str, username: str, chat_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._purge_expired_locked()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.username != username or job.chat_id != chat_id:
                return None
            return job.snapshot()

    def _purge_expired_locked(self) -> None:
        if not self._jobs:
            return
        cutoff = datetime.now(UTC) - timedelta(seconds=self._retention_seconds)
        expired_ids: list[str] = []
        for job_id, job in self._jobs.items():
            try:
                updated_at = datetime.fromisoformat(job.updated_at)
            except ValueError:
                updated_at = datetime.now(UTC)
            if updated_at < cutoff:
                expired_ids.append(job_id)
        for job_id in expired_ids:
            self._jobs.pop(job_id, None)
