from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any


class IUploadJobService(ABC):
    @abstractmethod
    def create_job(
        self,
        username: str,
        chat_id: str,
        original_names: Sequence[str],
        file_paths: Sequence[str],
        *,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Create a new upload job and return its state snapshot."""

    @abstractmethod
    def list_jobs(
        self,
        username: str,
        chat_id: str,
        *,
        limit: int = 20,
        include_terminal: bool = True,
    ) -> list[dict[str, Any]]:
        """List recent upload jobs for a user/chat pair."""

    @abstractmethod
    def retry_job(self, job_id: str, username: str, chat_id: str) -> dict[str, Any]:
        """Queue a failed job again when retry budget allows."""

    @abstractmethod
    def start_worker(self) -> None:
        """Start background upload worker loop."""

    @abstractmethod
    def stop_worker(self) -> None:
        """Stop background upload worker loop."""

    @abstractmethod
    def get_job(self, job_id: str, username: str, chat_id: str) -> dict[str, Any] | None:
        """Return the job snapshot if it belongs to the given user/chat."""
