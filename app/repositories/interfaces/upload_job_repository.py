from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any


class IUploadJobRepository(ABC):
    @abstractmethod
    def create_job(
        self,
        *,
        username: str,
        chat_id: str,
        original_names: Sequence[str],
        file_paths: Sequence[str],
        max_retries: int,
        message: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_job(self, *, job_id: str, username: str, chat_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def get_job_by_id(self, *, job_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_jobs(
        self,
        *,
        username: str,
        chat_id: str,
        limit: int = 20,
        include_terminal: bool = True,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def claim_next_queued_job(self) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def update_progress(
        self,
        *,
        job_id: str,
        stage: str | None = None,
        progress: int | None = None,
        files_processed: int | None = None,
        chunks_total: int | None = None,
        chunks_indexed: int | None = None,
        message: str | None = None,
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def mark_completed(
        self,
        *,
        job_id: str,
        files_processed: int,
        chunks_indexed: int,
        message: str,
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def mark_failed(
        self,
        *,
        job_id: str,
        error: str,
        message: str | None = None,
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def retry_job(self, *, job_id: str, username: str, chat_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def requeue_stale_processing_jobs(self, *, stale_seconds: int) -> int:
        raise NotImplementedError

    @abstractmethod
    def cleanup_expired_jobs(self, *, retention_seconds: int) -> int:
        raise NotImplementedError
