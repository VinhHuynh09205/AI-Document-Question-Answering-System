from __future__ import annotations

from collections.abc import Callable

from langchain_core.documents import Document


class RerankingService:
    def __init__(
        self,
        *,
        tokenize: Callable[[str], set[str]],
        calculate_overlap_score: Callable[[set[str], str], float],
        chunk_quality_penalty: Callable[[str, Document], float],
        chunk_quality_bonus: Callable[[Document], float],
    ) -> None:
        self._tokenize = tokenize
        self._calculate_overlap_score = calculate_overlap_score
        self._chunk_quality_penalty = chunk_quality_penalty
        self._chunk_quality_bonus = chunk_quality_bonus

    def rerank_documents(self, raw_question: str, docs: list[Document], top_k: int) -> list[Document]:
        if len(docs) <= 1:
            return docs

        question_tokens = self._tokenize(raw_question)
        source_counts: dict[str, int] = {}
        section_counts: dict[str, int] = {}
        for doc in docs:
            source = str(doc.metadata.get("source", ""))
            section = self._section_key(doc)
            source_counts[source] = source_counts.get(source, 0) + 1
            section_counts[section] = section_counts.get(section, 0) + 1

        scored: list[tuple[float, Document]] = []
        for index, doc in enumerate(docs):
            retrieval_score = float(doc.metadata.get("retrieval_score", 0.0))
            overlap_score = self._calculate_overlap_score(question_tokens, doc.page_content)
            source = str(doc.metadata.get("source", ""))
            section = self._section_key(doc)

            cohesion = 0.0
            cohesion += min(0.08, max(0, source_counts.get(source, 0) - 1) * 0.02)
            cohesion += min(0.05, max(0, section_counts.get(section, 0) - 1) * 0.015)
            position_bias = 1.0 - (index / max(1, len(docs)))
            quality_penalty = self._chunk_quality_penalty(raw_question, doc)
            quality_bonus = self._chunk_quality_bonus(doc)

            score = (
                (retrieval_score * 0.55)
                + (overlap_score * 0.32)
                + cohesion
                + (position_bias * 0.03)
                + quality_bonus
                - (quality_penalty * 0.25)
            )
            doc.metadata["rerank_score"] = round(score, 3)
            scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        limit = max(top_k, min(top_k * 2, 24))
        return [doc for _, doc in scored[:limit]]

    @staticmethod
    def _section_key(doc: Document) -> str:
        return str(
            doc.metadata.get("section_path")
            or doc.metadata.get("section_title")
            or doc.metadata.get("sheet_name")
            or doc.metadata.get("structure_path")
            or ""
        )