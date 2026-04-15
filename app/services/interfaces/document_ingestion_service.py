from abc import ABC, abstractmethod
from pathlib import Path
from typing import Sequence

from app.models.entities import UploadResult


class IDocumentIngestionService(ABC):
    @abstractmethod
    def ingest(
        self,
        file_paths: Sequence[Path],
        metadata: dict[str, str] | None = None,
    ) -> UploadResult:
        raise NotImplementedError
