import re
from typing import Sequence

from langchain_core.documents import Document

from app.services.interfaces.llm_provider import ILLMProvider
from app.services.qa_constants import FALLBACK_ANSWER

_SUMMARY_PATTERNS = re.compile(
    r"tóm tắt|tổng hợp|summarize|summary|overview|tổng quan|nội dung chính|main content|toàn bộ",
    re.IGNORECASE,
)


class LocalGroundedLLMProvider(ILLMProvider):
    def __init__(self, max_answer_chars: int) -> None:
        self._max_answer_chars = max_answer_chars

    def generate_grounded_answer(self, question: str, context_docs: Sequence[Document]) -> str:
        if not context_docs:
            return FALLBACK_ANSWER

        if _SUMMARY_PATTERNS.search(question):
            return self._build_full_summary(context_docs)

        question_tokens = self._tokenize(question)
        if not question_tokens:
            return self._build_full_summary(context_docs)

        ranked_sentences = self._rank_sentences(context_docs, question_tokens)
        best_sentences = [
            sentence for score, sentence in ranked_sentences if score >= 0.15
        ][:5]

        if not best_sentences:
            return self._build_full_summary(context_docs)

        answer = " ".join(best_sentences).strip()
        if not answer:
            return FALLBACK_ANSWER

        return answer[: self._max_answer_chars]

    def _build_full_summary(self, context_docs: Sequence[Document]) -> str:
        parts: list[str] = []
        for doc in context_docs:
            text = doc.page_content.strip()
            if text:
                parts.append(text)

        combined = "\n\n".join(parts).strip()
        if not combined:
            return FALLBACK_ANSWER

        return combined[: self._max_answer_chars]

    def _rank_sentences(
        self,
        context_docs: Sequence[Document],
        question_tokens: set[str],
    ) -> list[tuple[float, str]]:
        ranked: list[tuple[float, str]] = []

        for doc in context_docs:
            sentences = self._split_sentences(doc.page_content)
            for sentence in sentences:
                sentence_tokens = self._tokenize(sentence)
                if not sentence_tokens:
                    continue
                overlap = len(sentence_tokens & question_tokens)
                if overlap == 0:
                    continue
                score = overlap / len(question_tokens)
                ranked.append((score, sentence.strip()))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        raw_parts = re.split(r"(?<=[.!?])\s+|\n+", text)
        return [part.strip() for part in raw_parts if part.strip()]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"\w+", text)}
