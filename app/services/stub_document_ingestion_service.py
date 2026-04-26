from pathlib import Path
from typing import Sequence

from app.models.entities import UploadResult
from app.services.interfaces.document_ingestion_service import (
    IDocumentIngestionService,
    IngestionProgressCallback,
)


class StubDocumentIngestionService(IDocumentIngestionService):
    def ingest(
        self,
        file_paths: Sequence[Path],
        metadata: dict[str, str] | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> UploadResult:
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "completed",
                    "progress": 100,
                    "files_processed": len(file_paths),
                    "chunks_total": 0,
                    "chunks_indexed": 0,
                }
            )
        return UploadResult(files_processed=len(file_paths), chunks_indexed=0)
