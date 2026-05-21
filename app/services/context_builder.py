from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable

from langchain_core.documents import Document

from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.reranking_service import RerankingService


logger = logging.getLogger(__name__)


class ContextBuilder:
    def __init__(
        self,
        *,
        vector_store_repository: IVectorStoreRepository,
        reranking_service: RerankingService,
        build_retrieval_queries: Callable[[str, str], list[str]],
        tokenize: Callable[[str], set[str]],
        fold_text: Callable[[str], str],
        extract_focus_terms: Callable[[str], list[str]],
        metadata_alignment_boost: Callable[[str, Document], float],
        chunk_quality_penalty: Callable[[str, Document], float],
        chunk_quality_bonus: Callable[[Document], float],
        document_key: Callable[[Document], str],
        calculate_overlap_score: Callable[[set[str], str], float],
        normalize_text_query: Callable[[str], str],
    ) -> None:
        self._vector_store_repository = vector_store_repository
        self._reranking_service = reranking_service
        self._build_retrieval_queries = build_retrieval_queries
        self._tokenize = tokenize
        self._fold_text = fold_text
        self._extract_focus_terms = extract_focus_terms
        self._metadata_alignment_boost = metadata_alignment_boost
        self._chunk_quality_penalty = chunk_quality_penalty
        self._chunk_quality_bonus = chunk_quality_bonus
        self._document_key = document_key
        self._calculate_overlap_score = calculate_overlap_score
        self._normalize_text_query = normalize_text_query

    def merge_scoped_context_docs(
        self,
        *,
        raw_question: str,
        normalized_question: str,
        metadata_filter: dict[str, str | list[str]] | None,
        context_docs: list[Document],
        top_k: int,
        reranking_enabled: bool,
    ) -> list[Document]:
        scoped_docs = self.load_scoped_context_docs(metadata_filter)
        if not scoped_docs:
            return context_docs

        scoped_limit = self._resolve_scoped_context_limit(
            raw_question=raw_question,
            docs=scoped_docs,
            top_k=top_k,
        )
        ranked_scoped_docs = self.rank_scoped_context_docs(
            raw_question=raw_question,
            normalized_question=normalized_question,
            docs=scoped_docs,
            limit=scoped_limit,
        )
        if not ranked_scoped_docs:
            return context_docs

        coverage_docs = self._select_required_scope_coverage_docs(
            raw_question=raw_question,
            metadata_filter=metadata_filter,
            docs=[*ranked_scoped_docs, *scoped_docs],
        )

        merged_docs: list[Document] = []
        seen: set[str] = set()
        for doc in [*coverage_docs, *context_docs, *ranked_scoped_docs]:
            doc_key = self._document_key(doc)
            if doc_key in seen:
                continue
            seen.add(doc_key)
            merged_docs.append(doc)

        if not merged_docs:
            return []

        if len(merged_docs) > 1 and reranking_enabled:
            merged_docs = self._reranking_service.rerank_documents(raw_question, merged_docs, scoped_limit)

        return self.compress_context_docs(merged_docs, scoped_limit)

    def _resolve_scoped_context_limit(
        self,
        *,
        raw_question: str,
        docs: list[Document],
        top_k: int,
    ) -> int:
        default_limit = min(32, max(18, top_k * 4))
        if not docs:
            return default_limit

        if self._is_presentation_scope(docs):
            return max(default_limit, 24)

        folded_question = self._fold_text(raw_question)
        broad_request = re.search(
            r"\b(tom\s*tat|tong\s*quan|overview|summary|so\s*sanh|compare|toan\s*bo|all)\b",
            folded_question,
        )
        simple_fact_request = re.search(
            r"\b(ai|la\s*gi|bao\s*nhieu|may|nao|khi\s*nao|o\s*dau|viet\s*tat|khung\s*gio)\b",
            folded_question,
        )
        if simple_fact_request and not broad_request:
            return min(default_limit, max(8, top_k * 2))

        return default_limit

    @staticmethod
    def _is_presentation_scope(docs: list[Document]) -> bool:
        checked = 0
        presentation_docs = 0
        for doc in docs[:24]:
            checked += 1
            extension = str(doc.metadata.get("extension") or "").lower().lstrip(".")
            if extension in {"ppt", "pptx"} or doc.metadata.get("slide_number") is not None:
                presentation_docs += 1
        return checked > 0 and presentation_docs == checked

    def load_scoped_context_docs(
        self,
        metadata_filter: dict[str, str | list[str]] | None = None,
    ) -> list[Document]:
        if not metadata_filter:
            return []

        list_documents = getattr(self._vector_store_repository, "list_documents", None)
        if not callable(list_documents):
            return []

        scope_filter: dict[str, str | list[str]] = {}
        document_ids = self.extract_filter_values(metadata_filter, "document_id")
        if document_ids:
            scope_filter["document_id"] = document_ids[0] if len(document_ids) == 1 else document_ids
        else:
            sources = self.extract_filter_values(metadata_filter, "source")
            if not sources:
                return []
            scope_filter["source"] = sources[0] if len(sources) == 1 else sources

        try:
            docs = list_documents(metadata_filter=scope_filter)
        except Exception:
            logger.exception("qa_scoped_context_list_failed")
            return []

        filtered_docs: list[Document] = []
        seen: set[str] = set()
        for doc in docs:
            if not doc.page_content.strip():
                continue

            doc_key = self._document_key(doc)
            if doc_key in seen:
                continue
            seen.add(doc_key)
            filtered_docs.append(doc)

        return filtered_docs

    def _select_required_scope_coverage_docs(
        self,
        *,
        raw_question: str,
        metadata_filter: dict[str, str | list[str]] | None,
        docs: list[Document],
    ) -> list[Document]:
        if not metadata_filter or not docs:
            return []

        folded_question = self._fold_text(raw_question)
        if not re.search(
            r"\b(so\s*sanh|compare|doi\s*chieu|khac\s*biet|tuong\s*dong|tong\s*hop|vs)\b",
            folded_question,
        ):
            return []

        for key in ("source", "document_id"):
            required_values = self.extract_filter_values(metadata_filter, key)
            if len(required_values) < 2:
                continue

            required_set = set(required_values)
            selected: list[Document] = []
            seen_values: set[str] = set()
            for doc in docs:
                value = str(doc.metadata.get(key) or "").strip()
                if value not in required_set or value in seen_values:
                    continue
                selected.append(doc)
                seen_values.add(value)
                if len(seen_values) == len(required_set):
                    break

            if len(selected) >= 2:
                return selected

        return []

    @staticmethod
    def extract_filter_values(
        metadata_filter: dict[str, str | list[str]],
        key: str,
    ) -> list[str]:
        raw_value = metadata_filter.get(key)
        if isinstance(raw_value, list):
            unique_values: list[str] = []
            for item in raw_value:
                value = str(item or "").strip()
                if value and value not in unique_values:
                    unique_values.append(value)
            return unique_values

        value = str(raw_value or "").strip()
        return [value] if value else []

    @staticmethod
    def extract_single_filter_value(
        metadata_filter: dict[str, str | list[str]],
        key: str,
    ) -> str:
        values = ContextBuilder.extract_filter_values(metadata_filter, key)
        return values[0] if len(values) == 1 else ""

    def rank_scoped_context_docs(
        self,
        *,
        raw_question: str,
        normalized_question: str,
        docs: list[Document],
        limit: int,
    ) -> list[Document]:
        if not docs:
            return []

        queries = self._build_retrieval_queries(raw_question, normalized_question)
        query_token_sets: list[set[str]] = []
        for query in queries:
            query_tokens = self._tokenize(query)
            if query_tokens:
                query_token_sets.append(query_tokens)

        scored: list[tuple[float, Document]] = []
        for doc in docs:
            score = self.score_scoped_context_doc(
                raw_question=raw_question,
                query_token_sets=query_token_sets,
                doc=doc,
            )
            doc.metadata["scoped_score"] = round(score, 3)
            doc.metadata["retrieval_score"] = round(
                max(float(doc.metadata.get("retrieval_score", 0.0) or 0.0), score),
                3,
            )
            scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in scored[: max(1, limit)]]

    def score_scoped_context_doc(
        self,
        *,
        raw_question: str,
        query_token_sets: list[set[str]],
        doc: Document,
    ) -> float:
        best_overlap = 0.0
        for query_tokens in query_token_sets:
            overlap = self._calculate_overlap_score(query_tokens, doc.page_content)
            if overlap > best_overlap:
                best_overlap = overlap

        folded_content = self._fold_text(doc.page_content[:4000])
        focus_hits = 0
        for term in self._extract_focus_terms(raw_question)[:10]:
            if term in folded_content:
                focus_hits += 1

        metadata_boost = self._metadata_alignment_boost(raw_question, doc)
        quality_penalty = self._chunk_quality_penalty(raw_question, doc)
        exact_phrase_bonus = 0.0

        folded_question = self._fold_text(raw_question)
        if folded_question and len(folded_question) >= 16 and folded_question in folded_content:
            exact_phrase_bonus += 0.08

        section_value = str(
            doc.metadata.get("section_path")
            or doc.metadata.get("section_title")
            or doc.metadata.get("sheet_name")
            or ""
        ).strip()
        folded_section = self._fold_text(section_value)
        if folded_section and folded_section in folded_question:
            exact_phrase_bonus += 0.05

        quality_bonus = self._chunk_quality_bonus(doc)

        score = (
            (best_overlap * 0.7)
            + min(0.16, focus_hits * 0.03)
            + metadata_boost
            + exact_phrase_bonus
            + quality_bonus
            - (quality_penalty * 0.7)
        )
        return max(0.0, score)

    def compress_context_docs(self, docs: list[Document], max_docs: int) -> list[Document]:
        if not docs:
            return []

        deduplicated: list[Document] = []
        seen_hashes: set[str] = set()
        for doc in docs:
            normalized = self._normalize_text_query(re.sub(r"\s+", " ", doc.page_content))
            digest = hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            deduplicated.append(doc)

        compressed: list[Document] = []
        for doc in deduplicated:
            if not compressed:
                compressed.append(doc)
                continue

            previous = compressed[-1]
            if not self.can_merge_context_docs(previous, doc):
                compressed.append(doc)
                continue

            merged_content = f"{previous.page_content.strip()}\n{doc.page_content.strip()}".strip()
            if len(merged_content) > 2200:
                compressed.append(doc)
                continue

            merged_metadata = dict(previous.metadata)
            merged_metadata["merged_chunks"] = int(merged_metadata.get("merged_chunks", 1)) + 1
            compressed[-1] = Document(page_content=merged_content, metadata=merged_metadata)

        return compressed[:max_docs]

    @staticmethod
    def can_merge_context_docs(previous: Document, current: Document) -> bool:
        previous_source = str(previous.metadata.get("source", ""))
        current_source = str(current.metadata.get("source", ""))
        if previous_source != current_source:
            return False

        previous_section = str(
            previous.metadata.get("section_path")
            or previous.metadata.get("section_title")
            or previous.metadata.get("sheet_name")
            or previous.metadata.get("slide_number")
            or previous.metadata.get("structure_path")
            or ""
        )
        current_section = str(
            current.metadata.get("section_path")
            or current.metadata.get("section_title")
            or current.metadata.get("sheet_name")
            or current.metadata.get("slide_number")
            or current.metadata.get("structure_path")
            or ""
        )
        return previous_section == current_section
