import json
import logging
import math
import re
import time
from pathlib import Path
from shutil import copy2
from typing import Callable, Sequence

import faiss
import numpy as np
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.embeddings.embedding_cache import InMemoryEmbeddingCache
from app.services.interfaces.runtime_metrics import IRuntimeMetrics


logger = logging.getLogger(__name__)

_VECTOR_STORE_SCHEMA_VERSION = 3

_KEYWORD_TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:[._@:/\\-][A-Za-z0-9]+)+"
    r"|(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{3,}"
    r"|\b\d{2,}\b"
    r"|[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]{2,}"
    r"|[^\W\d_]{2,}",
    re.UNICODE,
)


class FaissVectorStoreRepository(IVectorStoreRepository):
    def __init__(
        self,
        index_dir: Path,
        embeddings: Embeddings,
        embedding_batch_size: int = 128,
        *,
        embedding_cache_enabled: bool = True,
        runtime_metrics: IRuntimeMetrics | None = None,
    ) -> None:
        self._index_dir = index_dir
        self._embeddings = embeddings
        self._embedding_batch_size = max(1, embedding_batch_size)
        self._embedding_cache = InMemoryEmbeddingCache(enabled=embedding_cache_enabled)
        self._runtime_metrics = runtime_metrics
        self._index_file = self._index_dir / "index.faiss"
        self._metadata_file = self._index_dir / "documents.json"
        self._manifest_file = self._index_dir / "manifest.json"
        self._index_dir.mkdir(parents=True, exist_ok=True)

        self._index: faiss.Index | None = None
        self._documents: list[dict] = []
        self._keyword_documents: list[dict[str, int | dict[str, int]]] = []
        self._avg_keyword_doc_length = 1.0
        self._requires_startup_rebuild = False
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

        provider_name, model_name = self._embedding_provider_details()
        cache_hits = 0
        cache_misses = 0
        vectors: list[list[float] | None] = [None] * len(valid_documents)
        uncached_texts: list[str] = []
        uncached_refs: list[tuple[int, str]] = []

        for index, doc in enumerate(valid_documents):
            cache_key = InMemoryEmbeddingCache.hash_text(doc.page_content)
            cached_vector = self._embedding_cache.get(cache_key)
            if cached_vector is not None:
                vectors[index] = cached_vector
                cache_hits += 1
                continue

            cache_misses += 1
            uncached_texts.append(doc.page_content)
            uncached_refs.append((index, cache_key))

        embedding_latency_ms = 0.0
        if uncached_texts:
            for start in range(0, len(uncached_texts), self._embedding_batch_size):
                batch_texts = uncached_texts[start:start + self._embedding_batch_size]
                batch_started_at = time.perf_counter()
                batch_vectors = self._embeddings.embed_documents(batch_texts)
                embedding_latency_ms += (time.perf_counter() - batch_started_at) * 1000.0

                for offset, vector in enumerate(batch_vectors):
                    ref_index = start + offset
                    if ref_index >= len(uncached_refs):
                        break
                    target_position, cache_key = uncached_refs[ref_index]
                    vectors[target_position] = vector
                    self._embedding_cache.set(cache_key, vector)

        total_added = 0
        for start in range(0, len(valid_documents), self._embedding_batch_size):
            batch_documents = valid_documents[start:start + self._embedding_batch_size]
            batch_vectors = vectors[start:start + self._embedding_batch_size]

            if any(vector is None for vector in batch_vectors):
                fallback_vectors = self._embeddings.embed_documents([doc.page_content for doc in batch_documents])
                for offset, vector in enumerate(fallback_vectors):
                    batch_vectors[offset] = vector

            matrix = np.asarray(batch_vectors, dtype="float32")
            if matrix.size == 0:
                continue

            if self._index is not None and self._index.ntotal != len(self._documents):
                logger.warning(
                    "faiss_index_payload_mismatch_on_add ntotal=%s payloads=%s resetting_index",
                    self._index.ntotal,
                    len(self._documents),
                )
                self._reset_index(matrix.shape[1])

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
                self._keyword_documents.append(self._build_keyword_payload(doc.page_content))

            total_added += len(batch_documents)
            if progress_callback is not None:
                progress_callback(total_added, len(valid_documents))

        self._refresh_keyword_average_length()

        if self._runtime_metrics is not None:
            self._runtime_metrics.increment_counter("cache_hits", cache_hits)
            self._runtime_metrics.increment_counter("cache_misses", cache_misses)
            self._runtime_metrics.record_gauge("average_embedding_batch_size", float(self._embedding_batch_size))
            self._runtime_metrics.record_pipeline_timing("embedding_generation_time_ms", embedding_latency_ms)

        logger.info(
            "embedding_batch_completed provider=%s model=%s batch_size=%s latency_ms=%.2f cache_hits=%s cache_misses=%s",
            provider_name,
            model_name,
            self._embedding_batch_size,
            embedding_latency_ms,
            cache_hits,
            cache_misses,
        )

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
            safe_doc_index = int(doc_index)
            if safe_doc_index >= len(self._documents):
                logger.warning(
                    "faiss_search_result_missing_payload index=%s payloads=%s ntotal=%s",
                    safe_doc_index,
                    len(self._documents),
                    self._index.ntotal if self._index is not None else 0,
                )
                continue
            payload = self._documents[safe_doc_index]
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

    def keyword_search(
        self,
        query: str,
        k: int,
        metadata_filter: dict[str, str | list[str]] | None = None,
    ) -> list[Document]:
        if not self._documents or not query.strip():
            return []

        tokens = self._tokenize_keywords(query)
        if not tokens:
            return []

        if len(self._keyword_documents) != len(self._documents):
            self._rebuild_keyword_index()

        total_documents = len(self._keyword_documents)
        if total_documents == 0:
            return []

        doc_freq: dict[str, int] = {token: 0 for token in tokens}
        for payload in self._keyword_documents:
            token_map = payload.get("freq", {}) if isinstance(payload, dict) else {}
            for token in tokens:
                if token in token_map:
                    doc_freq[token] += 1

        k1 = 1.2
        b = 0.75
        avg_len = max(1.0, self._avg_keyword_doc_length)
        scored: list[tuple[float, int]] = []

        for index, payload in enumerate(self._keyword_documents):
            metadata = self._documents[index].get("metadata", {})
            if metadata_filter and not self._match_metadata_filter(metadata, metadata_filter):
                continue

            token_map = payload.get("freq", {}) if isinstance(payload, dict) else {}
            doc_len = float(payload.get("length", 1) if isinstance(payload, dict) else 1)
            score = 0.0

            for token in tokens:
                tf = int(token_map.get(token, 0))
                if tf <= 0:
                    continue

                df = max(1, doc_freq.get(token, 0))
                idf = math.log(((total_documents - df + 0.5) / (df + 0.5)) + 1.0)
                numerator = tf * (k1 + 1.0)
                denominator = tf + (k1 * (1.0 - b + (b * (doc_len / avg_len))))
                score += idf * (numerator / max(1e-9, denominator))

            if score > 0:
                scored.append((score, index))

        if not scored:
            return []

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[: max(1, k)]
        results: list[Document] = []
        for score, index in selected:
            payload = self._documents[index]
            metadata = dict(payload.get("metadata", {}))
            metadata["keyword_score"] = round(float(score), 6)
            results.append(
                Document(
                    page_content=payload.get("page_content", ""),
                    metadata=metadata,
                )
            )

        return results

    def list_documents(
        self,
        metadata_filter: dict[str, str | list[str]] | None = None,
        limit: int | None = None,
    ) -> list[Document]:
        if not self._documents:
            return []

        results: list[Document] = []
        max_results = max(1, int(limit)) if limit is not None else None

        for payload in self._documents:
            metadata = payload.get("metadata", {})
            if metadata_filter and not self._match_metadata_filter(metadata, metadata_filter):
                continue

            results.append(
                Document(
                    page_content=payload.get("page_content", ""),
                    metadata=metadata,
                )
            )
            if max_results is not None and len(results) >= max_results:
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
        self._manifest_file.write_text(
            json.dumps(
                {
                    "schema_version": _VECTOR_STORE_SCHEMA_VERSION,
                    "document_count": len(self._documents),
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._requires_startup_rebuild = False

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
        if self._manifest_file.exists():
            copy2(self._manifest_file, backup_dir / self._manifest_file.name)

        return {
            "backed_up": True,
            "document_count": self.document_count(),
        }

    def restore(self, backup_dir: Path) -> dict:
        index_source = backup_dir / self._index_file.name
        metadata_source = backup_dir / self._metadata_file.name
        manifest_source = backup_dir / self._manifest_file.name

        if not index_source.exists() or not metadata_source.exists():
            return {
                "restored": False,
                "reason": "Backup files missing",
                "document_count": self.document_count(),
            }

        copy2(index_source, self._index_file)
        copy2(metadata_source, self._metadata_file)
        if manifest_source.exists():
            copy2(manifest_source, self._manifest_file)
        elif self._manifest_file.exists():
            self._manifest_file.unlink()
        self._load_existing_store()

        return {
            "restored": True,
            "document_count": self.document_count(),
        }

    def document_count(self) -> int:
        return len(self._documents)

    def delete_documents_by_metadata(self, metadata_filter: dict[str, str | list[str]]) -> int:
        if not metadata_filter or not self._documents:
            return 0

        kept_payloads: list[dict] = []
        kept_indices: list[int] = []
        removed_count = 0

        for index, payload in enumerate(self._documents):
            metadata = payload.get("metadata", {})
            if self._match_metadata_filter(metadata, metadata_filter):
                removed_count += 1
                continue
            kept_payloads.append(payload)
            kept_indices.append(index)

        if removed_count == 0:
            return 0

        if not kept_payloads:
            self._reset_index(None)
            return removed_count

        matrix = self._reconstruct_vectors_for_indices(kept_indices)
        if matrix is None:
            vectors = self._embeddings.embed_documents([payload["page_content"] for payload in kept_payloads])
            matrix = np.asarray(vectors, dtype="float32")

        if matrix.size == 0:
            self._reset_index(None)
            return removed_count

        rebuilt_index = faiss.IndexFlatL2(matrix.shape[1])
        rebuilt_index.add(matrix)

        self._index = rebuilt_index
        self._documents = kept_payloads
        self._rebuild_keyword_index()
        return removed_count

    def _reconstruct_vectors_for_indices(self, indices: list[int]) -> np.ndarray | None:
        if not indices or self._index is None:
            return None

        if self._index.ntotal != len(self._documents):
            logger.warning(
                "faiss_reconstruct_index_size_mismatch ntotal=%s payloads=%s",
                self._index.ntotal,
                len(self._documents),
            )
            return None

        try:
            matrix = np.empty((len(indices), self._index.d), dtype="float32")
            for out_index, source_index in enumerate(indices):
                matrix[out_index] = self._index.reconstruct(int(source_index))
            return matrix
        except Exception:
            logger.warning("faiss_reconstruct_failed_fallback_to_reembed", exc_info=True)
            return None

    def _reset_index(self, dimension: int | None) -> None:
        """Reset index when embedding provider changes or explicit clear is requested."""
        self._index = faiss.IndexFlatL2(dimension) if dimension is not None else None
        self._documents = []
        self._keyword_documents = []
        self._avg_keyword_doc_length = 1.0
        if self._index_file.exists():
            self._index_file.unlink()
        if self._metadata_file.exists():
            self._metadata_file.unlink()
        if self._manifest_file.exists():
            self._manifest_file.unlink()

    def clear(self) -> dict:
        self._reset_index(None)
        return {
            "cleared": True,
            "document_count": 0,
        }

    def requires_startup_rebuild(self) -> bool:
        return self._requires_startup_rebuild

    def _load_existing_store(self) -> None:
        if not self._index_file.exists() or not self._metadata_file.exists():
            return

        manifest_payload = self._load_manifest_payload()
        stored_schema_version = int(manifest_payload.get("schema_version", 0) or 0) if manifest_payload else 0
        if stored_schema_version != _VECTOR_STORE_SCHEMA_VERSION:
            logger.warning(
                "faiss_schema_mismatch expected=%s actual=%s index_dir=%s clearing_legacy_store",
                _VECTOR_STORE_SCHEMA_VERSION,
                stored_schema_version,
                self._index_dir,
            )
            self._requires_startup_rebuild = True
            self._reset_index(None)
            return

        try:
            self._index = faiss.read_index(str(self._index_file))
        except Exception:
            logger.exception(
                "faiss_index_load_failed clearing_store index_dir=%s",
                self._index_dir,
            )
            self._requires_startup_rebuild = True
            self._reset_index(None)
            return
        payload = self._metadata_file.read_text(encoding="utf-8").strip()
        self._documents = json.loads(payload) if payload else []

        manifest_document_count = int(manifest_payload.get("document_count", -1))
        index_document_count = int(self._index.ntotal)
        payload_document_count = len(self._documents)
        if (
            manifest_document_count != payload_document_count
            or index_document_count != payload_document_count
        ):
            logger.warning(
                "faiss_index_payload_mismatch_on_load manifest_count=%s index_count=%s payloads=%s index_dir=%s clearing_store",
                manifest_document_count,
                index_document_count,
                payload_document_count,
                self._index_dir,
            )
            self._requires_startup_rebuild = True
            self._reset_index(None)
            return

        self._rebuild_keyword_index()
        self._requires_startup_rebuild = False

    def _load_manifest_payload(self) -> dict[str, object] | None:
        if not self._manifest_file.exists():
            return None

        payload = self._manifest_file.read_text(encoding="utf-8").strip()
        if not payload:
            return None

        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else None

    def _embedding_provider_details(self) -> tuple[str, str]:
        provider = self._embeddings.__class__.__name__
        model_name = "unknown"

        for attr_name in ("model_name", "_model_name", "model"):
            value = getattr(self._embeddings, attr_name, "")
            if value:
                model_name = str(value)
                break

        return provider, model_name

    @staticmethod
    def _tokenize_keywords(text: str) -> list[str]:
        tokens: list[str] = []
        for raw_token in _KEYWORD_TOKEN_RE.findall(str(text or "")):
            token = str(raw_token).strip(" .,:;!?()[]{}<>\"'`|+")
            if len(token) <= 1:
                continue
            tokens.append(token.casefold())
        return tokens

    def _build_keyword_payload(self, text: str) -> dict[str, int | dict[str, int]]:
        frequencies: dict[str, int] = {}
        for token in self._tokenize_keywords(text):
            frequencies[token] = frequencies.get(token, 0) + 1
        return {
            "freq": frequencies,
            "length": max(1, sum(frequencies.values())),
        }

    def _refresh_keyword_average_length(self) -> None:
        if not self._keyword_documents:
            self._avg_keyword_doc_length = 1.0
            return

        total_length = 0
        for payload in self._keyword_documents:
            total_length += int(payload.get("length", 0) if isinstance(payload, dict) else 0)

        self._avg_keyword_doc_length = max(1.0, float(total_length) / len(self._keyword_documents))

    def _rebuild_keyword_index(self) -> None:
        self._keyword_documents = [
            self._build_keyword_payload(payload.get("page_content", ""))
            for payload in self._documents
        ]
        self._refresh_keyword_average_length()

    @staticmethod
    def _match_metadata_filter(metadata: dict, metadata_filter: dict[str, str | list[str]]) -> bool:
        def _normalize_extension(value: object) -> str:
            return str(value or "").strip().lower().lstrip(".")

        def _source_aliases() -> set[str]:
            aliases: set[str] = set()
            for metadata_key in ("source", "file_name", "document_name"):
                raw_value = str(metadata.get(metadata_key) or "").strip()
                if not raw_value:
                    continue
                aliases.add(raw_value)
                aliases.add(raw_value.replace("\\", "/").rsplit("/", 1)[-1])
                parts = raw_value.replace("\\", "/").rsplit("/", 1)[-1].split("_", 1)
                if len(parts) == 2 and len(parts[0]) >= 16:
                    aliases.add(parts[1])
            return {alias for alias in aliases if alias}

        def _matches_source_filter(value: object) -> bool:
            target = str(value or "").strip()
            if not target:
                return False
            target_basename = target.replace("\\", "/").rsplit("/", 1)[-1]
            aliases = _source_aliases()
            return target in aliases or target_basename in aliases

        for key, value in metadata_filter.items():
            metadata_value = str(metadata.get(key))

            if key == "extension":
                metadata_extension = _normalize_extension(metadata_value)
                if isinstance(value, list):
                    allowed_extensions = {_normalize_extension(item) for item in value}
                    if metadata_extension not in allowed_extensions:
                        return False
                    continue

                if metadata_extension != _normalize_extension(value):
                    return False
                continue

            if key == "source":
                if isinstance(value, list):
                    if not any(_matches_source_filter(item) for item in value):
                        return False
                    continue

                if not _matches_source_filter(value):
                    return False
                continue

            if isinstance(value, list):
                if metadata_value not in {str(item) for item in value}:
                    return False
                continue
            if metadata_value != str(value):
                return False
        return True
