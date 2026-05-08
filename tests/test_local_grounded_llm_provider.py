from langchain_core.documents import Document

from app.services.llm_providers.local_grounded_llm_provider import LocalGroundedLLMProvider
from app.services.qa_constants import FALLBACK_ANSWER


def test_local_summary_prefers_readable_segments_over_compacted_lines() -> None:
    provider = LocalGroundedLLMProvider(max_answer_chars=2000)
    docs = [
        Document(
            page_content=(
                "Môn học: Kiểm thử phần mềm\n"
                "GhilàicácphiênbảncủaPMtrongkhitest\n"
                "So sánh kết quả thực tế với kết quả mong đợi\n"
                "Viết báo cáo trạng thái kiểm thử"
            ),
            metadata={"source": "sample.pdf"},
        )
    ]

    answer = provider.generate_grounded_answer("Tóm tắt toàn bộ tài liệu", docs)

    assert "- Môn học: Kiểm thử phần mềm" in answer
    assert "- So sánh kết quả thực tế với kết quả mong đợi" in answer
    assert "GhilàicácphiênbảncủaPMtrongkhitest" not in answer


def test_compacted_text_detection_flags_unreadable_pdf_line() -> None:
    assert LocalGroundedLLMProvider._looks_like_compacted_text(
        "GhilàicácphiênbảncủaPMtrongkhitest"
    ) is True
    assert LocalGroundedLLMProvider._looks_like_compacted_text(
        "So sánh kết quả thực tế với kết quả mong đợi"
    ) is False


def test_local_provider_returns_fallback_for_translation_request() -> None:
    provider = LocalGroundedLLMProvider(max_answer_chars=2000)
    docs = [
        Document(
            page_content="Kiểm thử phần mềm giúp phát hiện lỗi sớm trong vòng đời phát triển.",
            metadata={"source": "sample.pdf"},
        )
    ]

    answer = provider.generate_grounded_answer("Dịch tài liệu sang tiếng Anh", docs)

    assert answer == FALLBACK_ANSWER