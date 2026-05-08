from collections.abc import Iterator
from typing import Sequence

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.interfaces.llm_provider import ILLMProvider
from app.services.llm_providers.prompt_contract import (
    build_visual_first_human_prompt,
    build_visual_first_system_prompt,
)
from app.services.qa_constants import FALLBACK_ANSWER


class OpenAILLMProvider(ILLMProvider):
    def __init__(self, api_key: str, model_name: str, max_answer_chars: int) -> None:
        self._max_answer_chars = max_answer_chars
        self._chain = (
            ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        build_visual_first_system_prompt(),
                    ),
                    (
                        "human",
                        build_visual_first_human_prompt(),
                    ),
                ]
            )
            | ChatOpenAI(api_key=api_key, model=model_name, temperature=0)
            | StrOutputParser()
        )

    def generate_grounded_answer(self, question: str, context_docs: Sequence[Document]) -> str:
        if not context_docs:
            return FALLBACK_ANSWER

        context = self._format_context(context_docs)
        if not context.strip():
            return FALLBACK_ANSWER

        try:
            answer = self._invoke_chain(question, context).strip()
        except Exception:
            return FALLBACK_ANSWER

        if not answer:
            return FALLBACK_ANSWER

        return answer[: self._max_answer_chars]

    def stream_grounded_answer(self, question: str, context_docs: Sequence[Document]) -> Iterator[str]:
        if not context_docs:
            yield FALLBACK_ANSWER
            return

        context = self._format_context(context_docs)
        if not context.strip():
            yield FALLBACK_ANSWER
            return

        try:
            total = 0
            for chunk in self._chain.stream({"question": question, "context": context}):
                if total + len(chunk) > self._max_answer_chars:
                    yield chunk[: self._max_answer_chars - total]
                    return
                yield chunk
                total += len(chunk)
        except Exception:
            yield FALLBACK_ANSWER

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=2))
    def _invoke_chain(self, question: str, context: str) -> str:
        return self._chain.invoke({"question": question, "context": context})

    @staticmethod
    def _format_context(context_docs: Sequence[Document]) -> str:
        parts: list[str] = []
        for index, doc in enumerate(context_docs, start=1):
            source = str(doc.metadata.get("source", "unknown"))
            page = doc.metadata.get("page")
            page_label = f" | page={page}" if page is not None else ""
            parts.append(f"[{index}] source={source}{page_label}\n{doc.page_content.strip()}")

        return "\n\n".join(parts)
