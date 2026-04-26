import logging
from pathlib import Path
from typing import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_core.documents import Document

from app.models.entities import UploadResult
from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.document_loader_registry import DocumentLoaderRegistry
from app.services.interfaces.document_ingestion_service import (
    IDocumentIngestionService,
    IngestionProgressCallback,
)
from app.services.text_chunking_service import TextChunkingService


logger = logging.getLogger(__name__)


class DocumentIngestionService(IDocumentIngestionService):
    def __init__(
        self,
        loader_registry: DocumentLoaderRegistry,
        chunking_service: TextChunkingService,
        vector_store_repository: IVectorStoreRepository,
        max_file_workers: int = 1,
    ) -> None:
        self._loader_registry = loader_registry
        self._chunking_service = chunking_service
        self._vector_store_repository = vector_store_repository
        self._max_file_workers = max(1, max_file_workers)

    def ingest(
        self,
        file_paths: Sequence[Path],
        metadata: dict[str, str] | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> UploadResult:
        files_total = len(file_paths)

        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "loading",
                    "progress": 5,
                    "files_processed": 0,
                    "chunks_total": 0,
                    "chunks_indexed": 0,
                }
            )

        loaded_documents = self._load_documents(file_paths, progress_callback=progress_callback)

        if metadata is not None:
            for doc in loaded_documents:
                doc.metadata.update(metadata)

        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "chunking",
                    "progress": 35,
                    "files_processed": files_total,
                    "chunks_total": 0,
                    "chunks_indexed": 0,
                }
            )

        chunks = self._chunking_service.split(loaded_documents)

        for index, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = index
            chunk.metadata["chunk_chars"] = len(chunk.page_content)

        chunks_total = len(chunks)

        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "indexing",
                    "progress": 40,
                    "files_processed": files_total,
                    "chunks_total": chunks_total,
                    "chunks_indexed": 0,
                }
            )

        def _on_index_progress(chunks_indexed: int, total_chunks: int) -> None:
            if progress_callback is None:
                return
            safe_total = max(1, total_chunks)
            indexed_ratio = chunks_indexed / safe_total
            progress_callback(
                {
                    "stage": "indexing",
                    "progress": 40 + int(indexed_ratio * 55),
                    "files_processed": files_total,
                    "chunks_total": total_chunks,
                    "chunks_indexed": chunks_indexed,
                }
            )

        chunks_indexed = self._vector_store_repository.add_documents(chunks, progress_callback=_on_index_progress)

        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "saving",
                    "progress": 98,
                    "files_processed": files_total,
                    "chunks_total": chunks_total,
                    "chunks_indexed": chunks_indexed,
                }
            )

        self._vector_store_repository.save()

        logger.info(
            "document_ingestion_completed files=%s loaded_docs=%s chunks_indexed=%s",
            len(file_paths),
            len(loaded_documents),
            chunks_indexed,
        )

        return UploadResult(
            files_processed=files_total,
            chunks_indexed=chunks_indexed,
        )

    def _load_documents(
        self,
        file_paths: Sequence[Path],
        progress_callback: IngestionProgressCallback | None = None,
    ) -> list[Document]:
        if not file_paths:
            return []

        total_files = len(file_paths)

        if self._max_file_workers <= 1 or len(file_paths) == 1:
            loaded_documents = []
            for index, file_path in enumerate(file_paths, start=1):
                loaded_documents.extend(self._loader_registry.load_file(file_path))
                if progress_callback is not None:
                    progress_callback(
                        {
                            "stage": "loading",
                            "progress": 5 + int((index / total_files) * 25),
                            "files_processed": index,
                        }
                    )
            return loaded_documents

        workers = min(self._max_file_workers, len(file_paths))
        documents_by_path: dict[Path, list[Document]] = {}

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ingestion-loader") as executor:
            future_to_path = {
                executor.submit(self._loader_registry.load_file, file_path): file_path
                for file_path in file_paths
            }
            completed_files = 0
            for future in as_completed(future_to_path):
                file_path = future_to_path[future]
                documents_by_path[file_path] = future.result()
                completed_files += 1
                if progress_callback is not None:
                    progress_callback(
                        {
                            "stage": "loading",
                            "progress": 5 + int((completed_files / total_files) * 25),
                            "files_processed": completed_files,
                        }
                    )

        loaded_documents = []
        for file_path in file_paths:
            loaded_documents.extend(documents_by_path.get(file_path, []))

        return loaded_documents
