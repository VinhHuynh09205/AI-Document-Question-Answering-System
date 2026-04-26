from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Sequence

from langchain_core.documents import Document


class IVectorStoreRepository(ABC):
    @abstractmethod
    def add_documents(
        self,
        documents: Sequence[Document],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def similarity_search(
        self,
        query: str,
        k: int,
        metadata_filter: dict[str, str | list[str]] | None = None,
    ) -> list[Document]:
        raise NotImplementedError

    @abstractmethod
    def save(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def backup(self, backup_dir: Path) -> dict:
        raise NotImplementedError

    @abstractmethod
    def restore(self, backup_dir: Path) -> dict:
        raise NotImplementedError

    @abstractmethod
    def document_count(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> dict:
        raise NotImplementedError
