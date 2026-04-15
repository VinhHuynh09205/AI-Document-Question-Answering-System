from pathlib import Path
from typing import Sequence

from app.models.entities import UploadResult
from app.services.interfaces.document_ingestion_service import IDocumentIngestionService


class StubDocumentIngestionService(IDocumentIngestionService):
    def ingest(self, file_paths: Sequence[Path]) -> UploadResult:
        return UploadResult(files_processed=len(file_paths), chunks_indexed=0)
