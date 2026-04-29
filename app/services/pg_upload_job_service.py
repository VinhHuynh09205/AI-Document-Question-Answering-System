from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from app.repositories.interfaces.upload_job_repository import IUploadJobRepository
from app.services.interfaces.document_ingestion_service import IDocumentIngestionService
from app.services.interfaces.upload_job_service import IUploadJobService
from app.services.interfaces.workspace_service import IWorkspaceService
from app.utils.file_hash import compute_file_sha256


logger = logging.getLogger(__name__)


class PgUploadJobService(IUploadJobService):
    def __init__(
        self,
        upload_job_repository: IUploadJobRepository,
        ingestion_service: IDocumentIngestionService,
        workspace_service: IWorkspaceService,
        *,
        retention_seconds: int = 3600,
        max_retries: int = 3,
        worker_poll_interval_seconds: float = 0.8,
        stale_processing_seconds: int = 120,
    ) -> None:
        self._upload_job_repository = upload_job_repository
        self._ingestion_service = ingestion_service
        self._workspace_service = workspace_service
        self._retention_seconds = max(300, int(retention_seconds))
        self._max_retries = max(0, int(max_retries))
        self._worker_poll_interval_seconds = max(0.2, float(worker_poll_interval_seconds))
        self._stale_processing_seconds = max(30, int(stale_processing_seconds))

        self._stop_event = Event()
        self._wake_event = Event()
        self._worker_lock = Lock()
        self._worker_thread: Thread | None = None

    def create_job(
        self,
        username: str,
        chat_id: str,
        original_names: Sequence[str],
        file_paths: Sequence[str],
        *,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        resolved_max_retries = self._max_retries if max_retries is None else max(0, int(max_retries))
        job = self._upload_job_repository.create_job(
            username=username,
            chat_id=chat_id,
            original_names=original_names,
            file_paths=file_paths,
            max_retries=resolved_max_retries,
            message="Đã nhận file, đang chờ xử lý",
        )
        self._wake_worker()
        return job

    def list_jobs(
        self,
        username: str,
        chat_id: str,
        *,
        limit: int = 20,
        include_terminal: bool = True,
    ) -> list[dict[str, Any]]:
        return self._upload_job_repository.list_jobs(
            username=username,
            chat_id=chat_id,
            limit=limit,
            include_terminal=include_terminal,
        )

    def retry_job(self, job_id: str, username: str, chat_id: str) -> dict[str, Any]:
        retried = self._upload_job_repository.retry_job(job_id=job_id, username=username, chat_id=chat_id)
        if retried is None:
            existing = self._upload_job_repository.get_job(job_id=job_id, username=username, chat_id=chat_id)
            if existing is None:
                raise ValueError("Upload job not found")
            if str(existing.get("status")) != "failed":
                raise ValueError("Only failed jobs can be retried")
            if int(existing.get("retry_count", 0)) >= int(existing.get("max_retries", 0)):
                raise ValueError("Retry limit exceeded")
            raise ValueError("Upload job cannot be retried")

        self._wake_worker()
        return retried

    def start_worker(self) -> None:
        with self._worker_lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return

            self._stop_event.clear()
            self._wake_event.clear()

            recovered = self._upload_job_repository.requeue_stale_processing_jobs(
                stale_seconds=self._stale_processing_seconds,
            )
            cleaned = self._upload_job_repository.cleanup_expired_jobs(
                retention_seconds=self._retention_seconds,
            )
            if recovered > 0:
                logger.info("upload_worker_recovered_stale_jobs count=%s", recovered)
            if cleaned > 0:
                logger.info("upload_worker_cleaned_expired_jobs count=%s", cleaned)

            self._worker_thread = Thread(
                target=self._worker_loop,
                name="upload-job-worker",
                daemon=True,
            )
            self._worker_thread.start()

    def stop_worker(self) -> None:
        with self._worker_lock:
            worker = self._worker_thread
            if worker is None:
                return
            self._stop_event.set()
            self._wake_event.set()

        worker.join(timeout=5)

        with self._worker_lock:
            if self._worker_thread is worker:
                self._worker_thread = None

    def get_job(self, job_id: str, username: str, chat_id: str) -> dict[str, Any] | None:
        return self._upload_job_repository.get_job(job_id=job_id, username=username, chat_id=chat_id)

    def _wake_worker(self) -> None:
        self._wake_event.set()

    def _worker_loop(self) -> None:
        last_cleanup_at = time.monotonic()

        while not self._stop_event.is_set():
            job = self._upload_job_repository.claim_next_queued_job()
            if job is None:
                now = time.monotonic()
                if now - last_cleanup_at >= 60:
                    self._upload_job_repository.cleanup_expired_jobs(
                        retention_seconds=self._retention_seconds,
                    )
                    last_cleanup_at = now

                self._wake_event.wait(timeout=self._worker_poll_interval_seconds)
                self._wake_event.clear()
                continue

            self._process_job(job)

    def _process_job(self, job: dict[str, Any]) -> None:
        job_id = str(job.get("job_id") or "")
        username = str(job.get("username") or "")
        chat_id = str(job.get("chat_id") or "")
        original_names = [str(name) for name in list(job.get("original_names") or [])]
        file_paths = [Path(str(path)) for path in list(job.get("file_paths") or []) if str(path).strip()]

        if not job_id or not username or not chat_id:
            logger.error("upload_worker_invalid_job_payload payload=%s", job)
            return

        if not file_paths:
            self._upload_job_repository.mark_failed(
                job_id=job_id,
                error="Upload job metadata is missing file paths",
                message="Upload processing failed",
            )
            return

        missing_paths = [str(path) for path in file_paths if not path.exists()]
        if missing_paths:
            self._upload_job_repository.mark_failed(
                job_id=job_id,
                error=f"Uploaded file missing on disk: {', '.join(missing_paths[:3])}",
                message="Upload processing failed",
            )
            return

        file_hashes: list[str] = []
        file_sizes: list[int] = []
        try:
            for path in file_paths:
                file_hash, file_size = compute_file_sha256(path)
                file_hashes.append(file_hash)
                file_sizes.append(file_size)
        except OSError:
            logger.exception("upload_worker_file_hash_failed job_id=%s", job_id)
            self._upload_job_repository.mark_failed(
                job_id=job_id,
                error="Failed to read uploaded file for hash validation",
                message="Upload processing failed",
            )
            return

        def _on_progress(progress_payload: dict[str, int | str]) -> None:
            raw_progress = progress_payload.get("progress")
            raw_files_processed = progress_payload.get("files_processed")
            raw_chunks_total = progress_payload.get("chunks_total")
            raw_chunks_indexed = progress_payload.get("chunks_indexed")

            self._upload_job_repository.update_progress(
                job_id=job_id,
                stage=str(progress_payload.get("stage", "processing")),
                progress=int(raw_progress) if isinstance(raw_progress, int) else None,
                files_processed=(
                    int(raw_files_processed)
                    if isinstance(raw_files_processed, int)
                    else None
                ),
                chunks_total=(
                    int(raw_chunks_total)
                    if isinstance(raw_chunks_total, int)
                    else None
                ),
                chunks_indexed=(
                    int(raw_chunks_indexed)
                    if isinstance(raw_chunks_indexed, int)
                    else None
                ),
            )

        try:
            result = self._ingestion_service.ingest(
                file_paths,
                {"owner": username, "chat_id": chat_id},
                _on_progress,
            )
            self._workspace_service.record_documents(
                username=username,
                chat_id=chat_id,
                saved_paths=file_paths,
                original_names=original_names,
                file_hashes=file_hashes,
                file_sizes=file_sizes,
            )
            self._upload_job_repository.mark_completed(
                job_id=job_id,
                files_processed=result.files_processed,
                chunks_indexed=result.chunks_indexed,
                message="Files uploaded successfully",
            )
        except Exception as exc:
            logger.exception("upload_worker_job_failed job_id=%s", job_id)
            self._upload_job_repository.mark_failed(
                job_id=job_id,
                error=self._extract_upload_error_detail(exc),
                message="Upload processing failed",
            )

    @staticmethod
    def _extract_upload_error_detail(exc: Exception) -> str:
        if isinstance(exc, RuntimeError) and "sentence-transformers" in str(exc):
            return (
                "Local semantic embeddings are not available. "
                "Set LOCAL_SEMANTIC_EMBEDDINGS=false or rebuild with local embedding dependencies."
            )
        return str(exc) or "Failed to process uploaded files"
