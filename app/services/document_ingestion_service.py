import logging
from pathlib import Path
from typing import Sequence

from app.models.entities import UploadResult
from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.document_loader_registry import DocumentLoaderRegistry
from app.services.interfaces.document_ingestion_service import IDocumentIngestionService
from app.services.text_chunking_service import TextChunkingService


logger = logging.getLogger(__name__)


class DocumentIngestionService(IDocumentIngestionService):
    def __init__(
        self,
        loader_registry: DocumentLoaderRegistry,
        chunking_service: TextChunkingService,
        vector_store_repository: IVectorStoreRepository,
    ) -> None:
        self._loader_registry = loader_registry
        self._chunking_service = chunking_service
        self._vector_store_repository = vector_store_repository

    def ingest(
        self,
        file_paths: Sequence[Path],
        metadata: dict[str, str] | None = None,
    ) -> UploadResult:
        loaded_documents = []

        for file_path in file_paths:
            loaded_documents.extend(self._loader_registry.load_file(file_path))

        if metadata is not None:
            for doc in loaded_documents:
                doc.metadata.update(metadata)

        chunks = self._chunking_service.split(loaded_documents)

        for index, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = index
            chunk.metadata["chunk_chars"] = len(chunk.page_content)

        chunks_indexed = self._vector_store_repository.add_documents(chunks)
        self._vector_store_repository.save()

        logger.info(
            "document_ingestion_completed files=%s loaded_docs=%s chunks_indexed=%s",
            len(file_paths),
            len(loaded_documents),
            chunks_indexed,
        )

        return UploadResult(
            files_processed=len(file_paths),
            chunks_indexed=chunks_indexed,
        )
