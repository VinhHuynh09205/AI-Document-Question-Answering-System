from collections.abc import Iterator
from typing import Sequence
import logging

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.services.interfaces.llm_provider import ILLMProvider
from app.services.llm_providers.local_grounded_llm_provider import LocalGroundedLLMProvider
from app.services.qa_constants import FALLBACK_ANSWER

logger = logging.getLogger(__name__)


class GeminiLLMProvider(ILLMProvider):
    def __init__(self, api_key: str, model_name: str, max_answer_chars: int) -> None:
        self._max_answer_chars = max_answer_chars
        self._local_fallback = LocalGroundedLLMProvider(max_answer_chars=max_answer_chars)
        self._chain = (
            ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "Bạn là trợ lý AI phân tích tài liệu chuyên nghiệp. "
                        "Trả lời bằng CÙNG ngôn ngữ với câu hỏi của người dùng. "
                        "Chỉ dùng thông tin trong CONTEXT để trả lời. "
                        "Hướng dẫn trả lời:\n"
                        "- Ưu tiên câu trả lời trực quan: kết hợp bullet list + bảng Markdown + sơ đồ Mermaid khi phù hợp.\n"
                        "- Với câu hỏi phân tích/tổng quan/so sánh, cố gắng kết hợp cả chữ + bảng + sơ đồ trong cùng câu trả lời.\n"
                        "- Tóm tắt: sử dụng 5-10 gạch đầu dòng ngắn gọn.\n"
                        "- Chi tiết: trích dẫn chính xác thông tin, số liệu từ CONTEXT.\n"
                        "- So sánh: tạo bảng Markdown chuẩn hoặc danh sách so sánh rõ ràng (không dùng bảng ASCII text).\n"
                        "- Nếu câu hỏi yêu cầu mindmap/sơ đồ/biểu đồ/đồ thị: trả về ít nhất 1 khối ```mermaid``` hợp lệ để hiển thị trực quan.\n"
                        "- Không mô phỏng hình vẽ bằng ký tự text (ASCII).\n"
                        "- Liệt kê: liệt kê đầy đủ tất cả mục tìm thấy.\n"
                        "- Luôn trả lời đầy đủ, chi tiết, không bịa thêm.\n"
                        f"- Nếu CONTEXT không chứa thông tin liên quan, trả đúng: {FALLBACK_ANSWER}",
                    ),
                    (
                        "human",
                        "QUESTION:\n{question}\n\nCONTEXT:\n{context}\n\n"
                        "Trả lời đầy đủ, chính xác dựa hoàn toàn trên CONTEXT. Ưu tiên định dạng trực quan và bao quát (bullet, bảng Markdown, Mermaid khi phù hợp).",
                    ),
                ]
            )
            | ChatGoogleGenerativeAI(
                google_api_key=api_key,
                model=model_name,
                temperature=0,
            )
            | StrOutputParser()
        )

    def generate_grounded_answer(self, question: str, context_docs: Sequence[Document]) -> str:
        if not context_docs:
            return FALLBACK_ANSWER

        context = self._format_context(context_docs)
        if not context.strip():
            return FALLBACK_ANSWER

        try:
            answer = self._chain.invoke({"question": question, "context": context}).strip()
        except Exception:
            logger.warning("gemini_api_failed, falling back to local provider")
            return self._local_fallback.generate_grounded_answer(question, context_docs)

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
            logger.warning("gemini_stream_failed, falling back to local provider")
            yield self._local_fallback.generate_grounded_answer(question, context_docs)

    @staticmethod
    def _format_context(context_docs: Sequence[Document]) -> str:
        parts: list[str] = []
        for index, doc in enumerate(context_docs, start=1):
            source = str(doc.metadata.get("source", "unknown"))
            page = doc.metadata.get("page")
            page_label = f" | page={page}" if page is not None else ""
            parts.append(f"[{index}] source={source}{page_label}\n{doc.page_content.strip()}")

        return "\n\n".join(parts)
