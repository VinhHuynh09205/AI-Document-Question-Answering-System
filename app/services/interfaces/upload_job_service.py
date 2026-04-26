from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any


class IUploadJobService(ABC):
    @abstractmethod
    def create_job(self, username: str, chat_id: str, original_names: Sequence[str]) -> dict[str, Any]:
        """Create a new upload job and return its state snapshot."""

    @abstractmethod
    def mark_processing(self, job_id: str, message: str | None = None) -> dict[str, Any] | None:
        """Mark a job as processing."""

    @abstractmethod
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
        """Update in-flight progress fields for a job."""

    @abstractmethod
    def mark_completed(
        self,
        job_id: str,
        *,
        files_processed: int,
        chunks_indexed: int,
        message: str,
    ) -> dict[str, Any] | None:
        """Mark a job as completed."""

    @abstractmethod
    def mark_failed(self, job_id: str, error: str, message: str | None = None) -> dict[str, Any] | None:
        """Mark a job as failed."""

    @abstractmethod
    def get_job(self, job_id: str, username: str, chat_id: str) -> dict[str, Any] | None:
        """Return the job snapshot if it belongs to the given user/chat."""
