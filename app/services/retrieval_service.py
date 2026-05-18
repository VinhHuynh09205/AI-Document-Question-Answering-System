from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from pathlib import Path

from langchain_core.documents import Document

from app.services.context_builder import ContextBuilder
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.query_router import QueryRouter
from app.services.reranking_service import RerankingService


logger = logging.getLogger(__name__)

_PPTX_DECK_OVERVIEW_HINT_RE = re.compile(
    r"\b(tong\s*quan\s*(slide|deck|presentation)|overview\s*(deck|slides?)|toan\s*bo\s*slide|all\s*slides?)\b",
    re.IGNORECASE,
)
_SPREADSHEET_LOOKUP_HINT_RE = re.compile(
    r"\b(sheet|excel|xlsx|xls|thi\s*sinh|hoc\s*vien|student|stt|id|no\.?\s*\d{1,4})\b",
    re.IGNORECASE,
)
_PPTX_OBJECT_HINT_RE = re.compile(
    r"\b(table|bang|bảng|chart|bieu\s*do|biểu\s*đồ|image|anh|ảnh|figure|hinh|hình)\b",
    re.IGNORECASE,
)


class RetrievalService:
    def __init__(
        self,
        *,
        vector_store_repository,
        query_router: QueryRouter,
        context_builder: ContextBuilder,
        reranking_service: RerankingService,
        runtime_metrics: IRuntimeMetrics | None,
        hybrid_retrieval_enabled: bool,
        reranking_enabled: bool,
        build_retrieval_queries: Callable[[str, str], list[str]],
        tokenize: Callable[[str], set[str]],
        fold_text: Callable[[str], str],
        metadata_alignment_boost: Callable[[str, Document], float],
        chunk_quality_penalty: Callable[[str, Document], float],
        chunk_quality_bonus: Callable[[Document], float],
        document_key: Callable[[Document], str],
        calculate_overlap_score: Callable[[set[str], str], float],
        canonical_sheet_name: Callable[[str], str],
        extract_sheet_hint: Callable[[str], str],
        extract_slide_number_hint: Callable[[str], int | None],
    ) -> None:
        self._vector_store_repository = vector_store_repository
        self._query_router = query_router
        self._context_builder = context_builder
        self._reranking_service = reranking_service
        self._runtime_metrics = runtime_metrics
        self._hybrid_retrieval_enabled = bool(hybrid_retrieval_enabled)
        self._reranking_enabled = bool(reranking_enabled)
        self._build_retrieval_queries = build_retrieval_queries
        self._tokenize = tokenize
        self._fold_text = fold_text
        self._metadata_alignment_boost = metadata_alignment_boost
        self._chunk_quality_penalty = chunk_quality_penalty
        self._chunk_quality_bonus = chunk_quality_bonus
        self._document_key = document_key
        self._calculate_overlap_score = calculate_overlap_score
        self._canonical_sheet_name = canonical_sheet_name
        self._extract_sheet_hint = extract_sheet_hint
        self._extract_slide_number_hint = extract_slide_number_hint

    def retrieve_context_docs(
        self,
        *,
        raw_question: str,
        normalized_question: str,
        metadata_filter: dict[str, str | list[str]] | None,
        top_k: int,
    ) -> list[Document]:
        retrieval_started_at = time.perf_counter()
        queries = self._build_retrieval_queries(raw_question, normalized_question)
        if not queries:
            return []

        effective_filter = self._query_router.build_metadata_filter(raw_question, metadata_filter)
        retrieval_limit = max(top_k, min(top_k * 2, 24))
        search_k = retrieval_limit if not self._hybrid_retrieval_enabled else max(retrieval_limit, top_k * 2)

        if self.is_pptx_scoped_filter(effective_filter):
            retrieval_limit = max(retrieval_limit, 20)
            search_k = max(search_k, 32)

        aggregated: dict[str, dict[str, object]] = {}
        for query in queries:
            try:
                docs = self._vector_store_repository.similarity_search(
                    query=query,
                    k=search_k,
                    metadata_filter=effective_filter,
                )
            except Exception:
                logger.exception("qa_retrieval_query_failed query=%s", query[:120])
                docs = []

            self.accumulate_ranked_docs(aggregated, docs, source="vector")

            if self._hybrid_retrieval_enabled and hasattr(self._vector_store_repository, "keyword_search"):
                try:
                    keyword_docs = self._vector_store_repository.keyword_search(
                        query=query,
                        k=search_k,
                        metadata_filter=effective_filter,
                    )
                except Exception:
                    logger.exception("qa_keyword_query_failed query=%s", query[:120])
                    keyword_docs = []

                self.accumulate_ranked_docs(aggregated, keyword_docs, source="keyword")

        if not aggregated:
            if self._runtime_metrics is not None:
                retrieval_latency_ms = (time.perf_counter() - retrieval_started_at) * 1000.0
                self._runtime_metrics.record_pipeline_timing("retrieval_time_ms", retrieval_latency_ms)
            return []

        question_tokens = self._tokenize(raw_question)
        scored_documents: list[tuple[float, Document]] = []
        for payload in aggregated.values():
            doc = payload["doc"]
            if not isinstance(doc, Document):
                continue

            score = self.score_retrieval_payload(
                payload=payload,
                question_tokens=question_tokens,
                raw_question=raw_question,
                top_k=search_k,
            )
            doc.metadata["retrieval_score"] = round(score, 3)
            scored_documents.append((score, doc))

        scored_documents.sort(key=lambda item: item[0], reverse=True)
        ranked_docs = [doc for _, doc in scored_documents[:retrieval_limit]]

        reranking_latency_ms = 0.0
        if self._reranking_enabled:
            reranking_started_at = time.perf_counter()
            ranked_docs = self._reranking_service.rerank_documents(raw_question, ranked_docs, retrieval_limit)
            reranking_latency_ms = (time.perf_counter() - reranking_started_at) * 1000.0
            if self._runtime_metrics is not None:
                self._runtime_metrics.record_pipeline_timing("reranking_time_ms", reranking_latency_ms)

        if _PPTX_DECK_OVERVIEW_HINT_RE.search(raw_question):
            ranked_docs = self.order_pptx_overview_docs(ranked_docs, top_k=top_k)

        compressed_docs = self._context_builder.compress_context_docs(ranked_docs, retrieval_limit)
        retrieval_latency_ms = (time.perf_counter() - retrieval_started_at) * 1000.0

        if self._runtime_metrics is not None:
            self._runtime_metrics.record_pipeline_timing("retrieval_time_ms", retrieval_latency_ms)
            self._runtime_metrics.increment_counter("retrieval_candidates", len(scored_documents))
            self._runtime_metrics.increment_counter("retrieval_selected_chunks", len(compressed_docs))

        logger.info(
            "[Retrieval] hybrid=%s reranking=%s queries=%s candidates=%s selected=%s retrieval_ms=%.2f reranking_ms=%.2f",
            self._hybrid_retrieval_enabled,
            self._reranking_enabled,
            len(queries),
            len(scored_documents),
            len(compressed_docs),
            retrieval_latency_ms,
            reranking_latency_ms,
        )

        return compressed_docs

    def accumulate_ranked_docs(
        self,
        aggregated: dict[str, dict[str, object]],
        docs: list[Document],
        source: str,
    ) -> None:
        hits_key = f"{source}_hits"
        rank_key = f"{source}_rank"

        for rank, doc in enumerate(docs):
            doc_key = self._document_key(doc)
            payload = aggregated.get(doc_key)
            if payload is None:
                payload = {
                    "doc": doc,
                    "vector_hits": 0,
                    "keyword_hits": 0,
                    "vector_rank": None,
                    "keyword_rank": None,
                    "keyword_score": 0.0,
                }
                aggregated[doc_key] = payload

            payload[hits_key] = int(payload.get(hits_key, 0)) + 1
            current_rank = payload.get(rank_key)
            if current_rank is None or rank < int(current_rank):
                payload[rank_key] = rank

            if source == "keyword":
                keyword_score = float(doc.metadata.get("keyword_score", 0.0) or 0.0)
                payload["keyword_score"] = max(float(payload.get("keyword_score", 0.0)), keyword_score)

    def score_retrieval_payload(
        self,
        *,
        payload: dict[str, object],
        question_tokens: set[str],
        raw_question: str,
        top_k: int,
    ) -> float:
        doc = payload.get("doc")
        if not isinstance(doc, Document):
            return 0.0

        vector_rank_raw = payload.get("vector_rank")
        keyword_rank_raw = payload.get("keyword_rank")
        vector_hits = int(payload.get("vector_hits", 0))
        keyword_hits = int(payload.get("keyword_hits", 0))

        overlap_score = self._calculate_overlap_score(question_tokens, doc.page_content)
        vector_component = 0.0
        if vector_rank_raw is not None:
            vector_component = 1.0 - (float(vector_rank_raw) / max(1.0, float(top_k)))

        keyword_component = 0.0
        if keyword_rank_raw is not None:
            keyword_component = max(keyword_component, 1.0 - (float(keyword_rank_raw) / max(1.0, float(top_k))))
        keyword_component = max(
            keyword_component,
            min(1.0, float(payload.get("keyword_score", 0.0)) / 8.0),
        )

        hit_component = min(vector_hits + keyword_hits, 4) / 4
        metadata_boost = self._metadata_alignment_boost(raw_question, doc)
        quality_penalty = self._chunk_quality_penalty(raw_question, doc)
        quality_bonus = self._chunk_quality_bonus(doc)

        final_score = (
            (overlap_score * 0.45)
            + (vector_component * 0.28)
            + (keyword_component * 0.17)
            + (hit_component * 0.10)
            + metadata_boost
            + quality_bonus
            - quality_penalty
        )

        folded_question = self._fold_text(raw_question)
        if _SPREADSHEET_LOOKUP_HINT_RE.search(folded_question):
            final_score += keyword_component * 0.08
            final_score += min(0.08, float(payload.get("keyword_score", 0.0)) / 10.0)

            target_sheet = self._extract_sheet_hint(folded_question)
            if target_sheet:
                sheet_name = str(doc.metadata.get("sheet_name") or doc.metadata.get("sheet") or "")
                if self._canonical_sheet_name(sheet_name) == target_sheet:
                    final_score += 0.05

        slide_hint = self._extract_slide_number_hint(raw_question)
        if slide_hint is not None:
            doc_slide = doc.metadata.get("slide_number") or doc.metadata.get("slide")
            if str(doc_slide) == str(slide_hint):
                final_score += 0.08
            else:
                final_score -= 0.08

        if _PPTX_OBJECT_HINT_RE.search(raw_question):
            final_score += keyword_component * 0.05

        doc.metadata["metadata_boost"] = round(metadata_boost, 3)
        doc.metadata["quality_penalty"] = round(quality_penalty, 3)
        return max(0.0, final_score)

    @staticmethod
    def order_pptx_overview_docs(docs: list[Document], *, top_k: int) -> list[Document]:
        if not docs:
            return docs

        ppt_docs = [
            doc for doc in docs
            if str(doc.metadata.get("extension") or "").lower().lstrip(".") in {"ppt", "pptx"}
            or doc.metadata.get("slide_number") is not None
        ]
        if len(ppt_docs) < 2:
            return docs

        grouped: dict[str, list[Document]] = {}
        for doc in ppt_docs:
            source = str(doc.metadata.get("source") or "")
            grouped.setdefault(source, []).append(doc)

        selected_source = max(grouped.items(), key=lambda item: len(item[1]))[0]
        ordered = sorted(
            grouped[selected_source],
            key=lambda doc: int(doc.metadata.get("slide_number") or doc.metadata.get("slide") or 10**6),
        )

        remainder = [doc for doc in docs if doc not in ordered]
        limit = max(top_k, min(top_k * 2, 24))
        return [*ordered, *remainder][:limit]

    @staticmethod
    def is_pptx_scoped_filter(metadata_filter: dict[str, str | list[str]] | None) -> bool:
        if not metadata_filter:
            return False

        extension_value = metadata_filter.get("extension")
        if extension_value is not None:
            normalized_extensions = QueryRouter.normalize_filter_values(extension_value)
            if normalized_extensions and all(value in {"ppt", "pptx"} for value in normalized_extensions):
                return True

        source_value = metadata_filter.get("source")
        if source_value is None:
            return False

        source_items = source_value if isinstance(source_value, list) else [source_value]
        suffixes = {
            Path(str(item or "")).suffix.lower().lstrip(".")
            for item in source_items
            if str(item or "").strip()
        }
        return bool(suffixes) and all(suffix in {"ppt", "pptx"} for suffix in suffixes)