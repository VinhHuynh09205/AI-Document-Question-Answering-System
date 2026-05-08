import logging
import re
import time
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.documents import Document

from app.models.entities import UploadResult
from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.document_loader_registry import DocumentLoaderRegistry
from app.services.interfaces.document_ingestion_service import (
    IDocumentIngestionService,
    IngestionProgressCallback,
)
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.text_chunking_service import TextChunkingService
from app.utils.file_hash import compute_file_sha256


logger = logging.getLogger(__name__)

_UUID_PREFIX_RE = re.compile(r"^[0-9a-f]{32}_(.+)$", re.IGNORECASE)


@dataclass(slots=True)
class _LoadedFile:
    path: Path
    documents: list[Document]
    file_hash: str
    file_size: int


class DocumentIngestionService(IDocumentIngestionService):
    def __init__(
        self,
        loader_registry: DocumentLoaderRegistry,
        chunking_service: TextChunkingService,
        vector_store_repository: IVectorStoreRepository,
        max_file_workers: int = 1,
        runtime_metrics: IRuntimeMetrics | None = None,
    ) -> None:
        self._loader_registry = loader_registry
        self._chunking_service = chunking_service
        self._vector_store_repository = vector_store_repository
        self._max_file_workers = max(1, max_file_workers)
        self._runtime_metrics = runtime_metrics

    def ingest(
        self,
        file_paths: Sequence[Path],
        metadata: dict[str, str] | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> UploadResult:
        ingestion_started_at = time.perf_counter()
        files_total = len(file_paths)
        if files_total == 0:
            return UploadResult(files_processed=0, chunks_indexed=0)

        chunking_time_ms = 0.0
        embedding_time_ms = 0.0
        vector_index_time_ms = 0.0
        total_chunks = 0
        total_indexed = 0
        global_chunk_index = 0
        base_metadata = dict(metadata or {})

        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "detecting_file_type",
                    "progress": 2,
                    "files_processed": 0,
                    "chunks_total": 0,
                    "chunks_indexed": 0,
                }
            )

        for files_processed, loaded_file in self._iter_loaded_files(file_paths):
            if progress_callback is not None:
                extraction_ratio = files_processed / max(1, files_total)
                progress_callback(
                    {
                        "stage": "extracting_content",
                        "progress": 5 + int(extraction_ratio * 20),
                        "files_processed": files_processed,
                        "chunks_total": total_chunks,
                        "chunks_indexed": total_indexed,
                    }
                )

            ocr_or_image_analysis_used = any(
                bool(doc.metadata.get("ocr_applied"))
                or bool(doc.metadata.get("image_analysis_applied"))
                for doc in loaded_file.documents
            )
            if ocr_or_image_analysis_used and progress_callback is not None:
                progress_callback(
                    {
                        "stage": "running_ocr",
                        "progress": 28 + int((files_processed / max(1, files_total)) * 6),
                        "files_processed": files_processed,
                        "chunks_total": total_chunks,
                        "chunks_indexed": total_indexed,
                    }
                )

            file_started_at = time.perf_counter()
            enriched_documents = self._enrich_loaded_documents(
                loaded_file=loaded_file,
                metadata=base_metadata,
            )

            if progress_callback is not None:
                progress_callback(
                    {
                        "stage": "cleaning_text",
                        "progress": 35 + int((files_processed / max(1, files_total)) * 7),
                        "files_processed": files_processed,
                        "chunks_total": total_chunks,
                        "chunks_indexed": total_indexed,
                    }
                )

            for document in enriched_documents:
                document.page_content = self._clean_document_text(document.page_content)

            chunk_started_at = time.perf_counter()
            chunks = self._chunking_service.split(enriched_documents)
            chunking_time_ms += (time.perf_counter() - chunk_started_at) * 1000.0

            for chunk in chunks:
                chunk.metadata["chunk_index"] = global_chunk_index
                chunk.metadata["chunk_chars"] = len(chunk.page_content)

                if "slide" in chunk.metadata and "slide_number" not in chunk.metadata:
                    chunk.metadata["slide_number"] = chunk.metadata.get("slide")
                if "sheet" in chunk.metadata and "sheet_name" not in chunk.metadata:
                    chunk.metadata["sheet_name"] = chunk.metadata.get("sheet")
                if "section_title" not in chunk.metadata:
                    chunk.metadata["section_title"] = "overview"

                global_chunk_index += 1

            total_chunks += len(chunks)

            if progress_callback is not None:
                progress_callback(
                    {
                        "stage": "chunking",
                        "progress": 45 + int((files_processed / max(1, files_total)) * 10),
                        "files_processed": files_processed,
                        "chunks_total": total_chunks,
                        "chunks_indexed": total_indexed,
                    }
                )

            if chunks:
                add_started_at = time.perf_counter()

                def _on_index_progress(chunks_indexed: int, current_total: int) -> None:
                    if progress_callback is None:
                        return
                    projected_indexed = total_indexed + chunks_indexed
                    safe_total = max(total_chunks, projected_indexed, current_total, 1)
                    ratio = projected_indexed / safe_total
                    progress_callback(
                        {
                            "stage": "generating_embeddings",
                            "progress": 56 + int(ratio * 36),
                            "files_processed": files_processed,
                            "chunks_total": safe_total,
                            "chunks_indexed": projected_indexed,
                        }
                    )

                indexed_now = self._vector_store_repository.add_documents(
                    chunks,
                    progress_callback=_on_index_progress,
                )
                elapsed_add_ms = (time.perf_counter() - add_started_at) * 1000.0
                embedding_time_ms += elapsed_add_ms
                vector_index_time_ms += elapsed_add_ms
                total_indexed += indexed_now

            file_duration_ms = (time.perf_counter() - file_started_at) * 1000.0
            logger.info(
                "ingestion_file_processed file_name=%s file_size=%s chunk_count=%s ingestion_duration_ms=%.2f",
                self._safe_document_name(loaded_file.path.name),
                loaded_file.file_size,
                len(chunks),
                file_duration_ms,
            )

        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "saving_vector_index",
                    "progress": 97,
                    "files_processed": files_total,
                    "chunks_total": total_chunks,
                    "chunks_indexed": total_indexed,
                }
            )

        save_started_at = time.perf_counter()
        self._vector_store_repository.save()
        vector_index_time_ms += (time.perf_counter() - save_started_at) * 1000.0

        ingestion_total_time_ms = (time.perf_counter() - ingestion_started_at) * 1000.0

        self._record_timing("ingestion_total_time_ms", ingestion_total_time_ms)
        self._record_timing("chunking_time_ms", chunking_time_ms)
        self._record_timing("embedding_generation_time_ms", embedding_time_ms)
        self._record_timing("vector_index_time_ms", vector_index_time_ms)
        self._record_gauge("average_embedding_batch_size", total_chunks / max(1, files_total))

        logger.info(
            "document_ingestion_completed files=%s chunks_total=%s chunks_indexed=%s ingestion_total_time_ms=%.2f",
            len(file_paths),
            total_chunks,
            total_indexed,
            ingestion_total_time_ms,
        )

        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "completed",
                    "progress": 100,
                    "files_processed": files_total,
                    "chunks_total": total_chunks,
                    "chunks_indexed": total_indexed,
                }
            )

        return UploadResult(
            files_processed=files_total,
            chunks_indexed=total_indexed,
        )

    def _iter_loaded_files(
        self,
        file_paths: Sequence[Path],
    ) -> Iterator[tuple[int, _LoadedFile]]:
        if not file_paths:
            return

        workers = min(self._max_file_workers, len(file_paths))

        if workers <= 1:
            for index, file_path in enumerate(file_paths, start=1):
                yield index, self._load_file_bundle(file_path)
            return

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ingestion-loader") as executor:
            future_to_path = {
                executor.submit(self._load_file_bundle, file_path): file_path
                for file_path in file_paths
            }

            completed = 0
            for future in as_completed(future_to_path):
                loaded_file = future.result()
                completed += 1
                yield completed, loaded_file

    def _load_file_bundle(self, file_path: Path) -> _LoadedFile:
        documents = self._loader_registry.load_file(file_path)
        file_hash, file_size = compute_file_sha256(file_path)
        return _LoadedFile(
            path=file_path,
            documents=documents,
            file_hash=file_hash,
            file_size=file_size,
        )

    def _enrich_loaded_documents(
        self,
        *,
        loaded_file: _LoadedFile,
        metadata: dict[str, str],
    ) -> list[Document]:
        file_path = loaded_file.path
        normalized_type = file_path.suffix.lower().lstrip(".")
        now_iso = datetime.now(UTC).isoformat()
        workspace_id = str(metadata.get("chat_id") or metadata.get("workspace_id") or "")
        username = str(metadata.get("owner") or metadata.get("username") or "")
        version_raw = str(metadata.get("version") or "1")
        try:
            version = max(1, int(version_raw))
        except ValueError:
            version = 1

        base_document_name = self._safe_document_name(file_path.name)

        enriched: list[Document] = []
        for doc in loaded_file.documents:
            enriched_metadata = dict(doc.metadata)
            enriched_metadata.update(metadata)

            source_path = str(enriched_metadata.get("source") or str(file_path))
            extension = str(enriched_metadata.get("extension") or file_path.suffix.lower())
            document_name = self._safe_document_name(Path(source_path).name)

            enriched_metadata.setdefault("source", source_path)
            enriched_metadata.setdefault("extension", extension)
            enriched_metadata.setdefault("document_id", self._build_document_id(loaded_file.file_hash, source_path))
            enriched_metadata.setdefault("document_name", document_name or base_document_name)
            enriched_metadata.setdefault("document_type", normalized_type)
            enriched_metadata.setdefault("file_hash", loaded_file.file_hash)
            enriched_metadata.setdefault("created_at", now_iso)
            enriched_metadata.setdefault("workspace_id", workspace_id)
            enriched_metadata.setdefault("username", username)
            enriched_metadata.setdefault("version", version)

            if "slide" in enriched_metadata and "slide_number" not in enriched_metadata:
                enriched_metadata["slide_number"] = enriched_metadata.get("slide")
            if "sheet" in enriched_metadata and "sheet_name" not in enriched_metadata:
                enriched_metadata["sheet_name"] = enriched_metadata.get("sheet")
            if "section_title" not in enriched_metadata:
                enriched_metadata["section_title"] = "overview"

            enriched.append(
                Document(
                    page_content=doc.page_content,
                    metadata=enriched_metadata,
                )
            )

        return enriched

    @staticmethod
    def _safe_document_name(raw_name: str) -> str:
        candidate = str(raw_name or "").strip()
        match = _UUID_PREFIX_RE.match(candidate)
        if match:
            return match.group(1)
        return candidate

    @staticmethod
    def _build_document_id(file_hash: str, source_path: str) -> str:
        seed = f"{file_hash}:{source_path}".encode("utf-8", errors="ignore")
        return hashlib.sha256(seed).hexdigest()[:32]

    @staticmethod
    def _clean_document_text(raw_text: str) -> str:
        normalized = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
        normalized = "".join(
            ch for ch in normalized
            if ch in {"\n", "\t"} or ord(ch) >= 32
        )
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    def _record_timing(self, metric_name: str, value_ms: float) -> None:
        if self._runtime_metrics is None:
            return
        if hasattr(self._runtime_metrics, "record_pipeline_timing"):
            self._runtime_metrics.record_pipeline_timing(metric_name, value_ms)

    def _record_gauge(self, metric_name: str, value: float) -> None:
        if self._runtime_metrics is None:
            return
        if hasattr(self._runtime_metrics, "record_gauge"):
            self._runtime_metrics.record_gauge(metric_name, value)
