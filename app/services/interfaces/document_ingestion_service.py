from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Sequence

from app.models.entities import UploadResult


IngestionProgressCallback = Callable[[dict[str, int | str]], None]


class IDocumentIngestionService(ABC):
    @abstractmethod
    def ingest(
        self,
        file_paths: Sequence[Path],
        metadata: dict[str, str] | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> UploadResult:
        raise NotImplementedError
