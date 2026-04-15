from collections.abc import Iterator
from typing import Sequence

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.interfaces.llm_provider import ILLMProvider
from app.services.qa_constants import FALLBACK_ANSWER


class GroqLLMProvider(ILLMProvider):
    def __init__(self, api_key: str, model_name: str, max_answer_chars: int) -> None:
        self._max_answer_chars = max_answer_chars
        self._chain = (
            ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "Bạn là trợ lý phân tích tài liệu chuyên nghiệp và chính xác. "
                        "Trả lời bằng CÙNG ngôn ngữ với câu hỏi của người dùng. "
                        "Chỉ dùng thông tin trong CONTEXT bên dưới. "
                        "Hướng dẫn trả lời:\n"
                        "- Nếu câu hỏi yêu cầu tóm tắt: tóm tắt toàn bộ CONTEXT thành 5-10 gạch đầu dòng rõ ràng.\n"
                        "- Nếu câu hỏi hỏi về chi tiết cụ thể: trích dẫn chính xác thông tin từ CONTEXT.\n"
                        "- Nếu câu hỏi yêu cầu so sánh: tạo bảng hoặc danh sách so sánh.\n"
                        "- Nếu câu hỏi yêu cầu liệt kê: liệt kê đầy đủ các mục tìm thấy.\n"
                        "- Luôn trả lời chi tiết, đầy đủ nhưng không bịa thêm dữ liệu ngoài CONTEXT.\n"
                        "- Trích dẫn số liệu, tên, ngày tháng chính xác từ CONTEXT khi có.\n"
                        f"- Nếu CONTEXT không chứa thông tin liên quan, trả đúng: {FALLBACK_ANSWER}",
                    ),
                    (
                        "human",
                        "QUESTION:\n{question}\n\nCONTEXT:\n{context}\n\n"
                        "Trả lời đầy đủ, chính xác dựa trên tài liệu. Sử dụng định dạng phù hợp (bullet list, bảng, đoạn văn) tùy theo câu hỏi.",
                    ),
                ]
            )
            | ChatGroq(api_key=api_key, model=model_name, temperature=0)
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
