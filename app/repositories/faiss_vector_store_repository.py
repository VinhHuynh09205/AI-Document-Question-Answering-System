import json
import logging
from pathlib import Path
from shutil import copy2
from typing import Callable, Sequence

import faiss
import numpy as np
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository


logger = logging.getLogger(__name__)


class FaissVectorStoreRepository(IVectorStoreRepository):
    def __init__(self, index_dir: Path, embeddings: Embeddings, embedding_batch_size: int = 128) -> None:
        self._index_dir = index_dir
        self._embeddings = embeddings
        self._embedding_batch_size = max(1, embedding_batch_size)
        self._index_file = self._index_dir / "index.faiss"
        self._metadata_file = self._index_dir / "documents.json"
        self._index_dir.mkdir(parents=True, exist_ok=True)

        self._index: faiss.Index | None = None
        self._documents: list[dict] = []
        self._load_existing_store()

    def add_documents(
        self,
        documents: Sequence[Document],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        valid_documents = [doc for doc in documents if doc.page_content.strip()]
        if not valid_documents:
            if progress_callback is not None:
                progress_callback(0, 0)
            return 0

        total_added = 0
        for start in range(0, len(valid_documents), self._embedding_batch_size):
            batch_documents = valid_documents[start:start + self._embedding_batch_size]
            vectors = self._embeddings.embed_documents([doc.page_content for doc in batch_documents])
            matrix = np.asarray(vectors, dtype="float32")
            if matrix.size == 0:
                continue

            if self._index is None:
                self._index = faiss.IndexFlatL2(matrix.shape[1])
            elif matrix.shape[1] != self._index.d:
                logger.warning(
                    "faiss_dimension_mismatch_on_add existing_dim=%s new_dim=%s resetting_index",
                    self._index.d,
                    matrix.shape[1],
                )
                self._reset_index(matrix.shape[1])

            self._index.add(matrix)
            for doc in batch_documents:
                self._documents.append(
                    {
                        "page_content": doc.page_content,
                        "metadata": doc.metadata,
                    }
                )
            total_added += len(batch_documents)
            if progress_callback is not None:
                progress_callback(total_added, len(valid_documents))

        return total_added

    def similarity_search(
        self,
        query: str,
        k: int,
        metadata_filter: dict[str, str | list[str]] | None = None,
    ) -> list[Document]:
        if self._index is None or not self._documents:
            return []

        safe_k = len(self._documents) if metadata_filter else max(1, min(k, len(self._documents)))
        query_vector = np.array([self._embeddings.embed_query(query)], dtype="float32")

        if query_vector.shape[1] != self._index.d:
            logger.warning(
                "faiss_dimension_mismatch_on_search index_dim=%s query_dim=%s returning_empty",
                self._index.d,
                query_vector.shape[1],
            )
            return []

        _, indices = self._index.search(query_vector, safe_k)

        results: list[Document] = []
        for doc_index in indices[0]:
            if doc_index < 0:
                continue
            payload = self._documents[int(doc_index)]
            metadata = payload.get("metadata", {})
            if metadata_filter and not self._match_metadata_filter(metadata, metadata_filter):
                continue
            results.append(
                Document(
                    page_content=payload["page_content"],
                    metadata=metadata,
                )
            )
            if len(results) >= k:
                break

        return results

    def save(self) -> None:
        if self._index is None:
            return

        faiss.write_index(self._index, str(self._index_file))
        self._metadata_file.write_text(
            json.dumps(self._documents, ensure_ascii=True, indent=2, default=str),
            encoding="utf-8",
        )

    def backup(self, backup_dir: Path) -> dict:
        self.save()
        backup_dir.mkdir(parents=True, exist_ok=True)

        if not self._index_file.exists() or not self._metadata_file.exists():
            return {
                "backed_up": False,
                "reason": "No index files found",
                "document_count": self.document_count(),
            }

        copy2(self._index_file, backup_dir / self._index_file.name)
        copy2(self._metadata_file, backup_dir / self._metadata_file.name)

        return {
            "backed_up": True,
            "document_count": self.document_count(),
        }

    def restore(self, backup_dir: Path) -> dict:
        index_source = backup_dir / self._index_file.name
        metadata_source = backup_dir / self._metadata_file.name

        if not index_source.exists() or not metadata_source.exists():
            return {
                "restored": False,
                "reason": "Backup files missing",
                "document_count": self.document_count(),
            }

        copy2(index_source, self._index_file)
        copy2(metadata_source, self._metadata_file)
        self._load_existing_store()

        return {
            "restored": True,
            "document_count": self.document_count(),
        }

    def document_count(self) -> int:
        return len(self._documents)

    def _reset_index(self, dimension: int | None) -> None:
        """Reset index when embedding provider changes or explicit clear is requested."""
        self._index = faiss.IndexFlatL2(dimension) if dimension is not None else None
        self._documents = []
        if self._index_file.exists():
            self._index_file.unlink()
        if self._metadata_file.exists():
            self._metadata_file.unlink()

    def clear(self) -> dict:
        self._reset_index(None)
        return {
            "cleared": True,
            "document_count": 0,
        }

    def _load_existing_store(self) -> None:
        if not self._index_file.exists() or not self._metadata_file.exists():
            return

        self._index = faiss.read_index(str(self._index_file))
        payload = self._metadata_file.read_text(encoding="utf-8").strip()
        self._documents = json.loads(payload) if payload else []

    @staticmethod
    def _match_metadata_filter(metadata: dict, metadata_filter: dict[str, str | list[str]]) -> bool:
        for key, value in metadata_filter.items():
            metadata_value = str(metadata.get(key))
            if isinstance(value, list):
                if metadata_value not in {str(item) for item in value}:
                    return False
                continue
            if metadata_value != str(value):
                return False
        return True
