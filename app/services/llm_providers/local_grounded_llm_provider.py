import re
from typing import Sequence

from langchain_core.documents import Document

from app.services.interfaces.llm_provider import ILLMProvider
from app.services.qa_constants import FALLBACK_ANSWER

_SUMMARY_PATTERNS = re.compile(
    r"tóm tắt|tổng hợp|summarize|summary|overview|tổng quan|nội dung chính|main content|toàn bộ",
    re.IGNORECASE,
)
_UNSUPPORTED_TRANSFORM_PATTERNS = re.compile(
    r"dịch|dich|translate|quiz|trắc\s*nghiệm|trac\s*nghiem|multiple\s*choice|"
    r"slide|presentation|thuyết\s*trình|thuyet\s*trinh|rút\s*gọn|rut\s*gon|shorten|"
    r"viết\s*lại|viet\s*lai|học\s*thuật|hoc\s*thuat|academic\s*style",
    re.IGNORECASE,
)


class LocalGroundedLLMProvider(ILLMProvider):
    def __init__(self, max_answer_chars: int) -> None:
        self._max_answer_chars = max_answer_chars

    def generate_grounded_answer(self, question: str, context_docs: Sequence[Document]) -> str:
        if not context_docs:
            return FALLBACK_ANSWER

        if _UNSUPPORTED_TRANSFORM_PATTERNS.search(question or ""):
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
        segments = self._collect_readable_segments(context_docs, limit=8)
        if segments:
            summary = "\n".join(f"- {segment}" for segment in segments)
            return summary[: self._max_answer_chars]

        parts: list[str] = []
        for doc in context_docs:
            text = self._normalize_segment(doc.page_content)
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

    @classmethod
    def _collect_readable_segments(cls, context_docs: Sequence[Document], limit: int = 8) -> list[str]:
        segments: list[str] = []
        seen: set[str] = set()

        for doc in context_docs:
            for segment in cls._split_sentences(doc.page_content):
                normalized = cls._normalize_segment(segment)
                if not normalized:
                    continue

                key = normalized.lower()
                if key in seen:
                    continue

                seen.add(key)
                segments.append(normalized)
                if len(segments) >= limit:
                    return segments

        return segments

    @classmethod
    def _split_sentences(cls, text: str) -> list[str]:
        raw_parts = re.split(r"(?<=[.!?])\s+|\n+", text)
        sentences: list[str] = []

        for part in raw_parts:
            normalized = cls._normalize_segment(part)
            if normalized:
                sentences.append(normalized)

        return sentences

    @staticmethod
    def _normalize_segment(text: str) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "").replace("\u00A0", " ")).strip(" -•\t")
        if not normalized:
            return ""
        if LocalGroundedLLMProvider._looks_like_compacted_text(normalized):
            return ""
        return normalized

    @staticmethod
    def _looks_like_compacted_text(text: str) -> bool:
        alphabetic_chars = re.findall(r"[A-Za-zÀ-ỹ]", text)
        if len(alphabetic_chars) < 18:
            return False
        if len(text.split()) >= 3:
            return False

        punctuation_count = len(re.findall(r"[:;,.()\-/]", text))
        return punctuation_count == 0

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"\w+", text)}
