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


def test_local_provider_returns_fallback_instead_of_raw_slide_metadata_for_specific_question() -> None:
    provider = LocalGroundedLLMProvider(max_answer_chars=2000)
    docs = [
        Document(
            page_content=(
                "File: Test pptx.pptx\n"
                "Slide: 13\n"
                "Title: 日本人は、どんな人と一緒に仕事がしたいと考えていますか？\n"
                "Layout: TitleSlide\n"
                "Slide Blocks:\n"
                "- [1] textbox/auto_shape @ x=1,y=2,w=3,h=4: 日本の文化・習慣を理解している人\n"
            ),
            metadata={"source": "deck.pptx"},
        )
    ]

    answer = provider.generate_grounded_answer("Thông điệp về khác biệt văn hóa là gì?", docs)

    assert answer == FALLBACK_ANSWER


def test_local_summary_omits_structural_slide_metadata_and_keeps_meaningful_block_text() -> None:
    provider = LocalGroundedLLMProvider(max_answer_chars=2000)
    docs = [
        Document(
            page_content=(
                "File: Test pptx.pptx\n"
                "Slide: 14\n"
                "Title: 日本人は、どんな人と一緒に仕事がしたいと考えていますか？\n"
                "Layout: TitleAndContent\n"
                "Slide Blocks:\n"
                "- [1] textbox/auto_shape @ x=1,y=2,w=3,h=4: 日本の文化・習慣を理解している人\n"
                "- [2] textbox/auto_shape @ x=1,y=5,w=3,h=4: 素直な人\n"
            ),
            metadata={"source": "deck.pptx"},
        )
    ]

    answer = provider.generate_grounded_answer("Tóm tắt toàn bộ tài liệu", docs)

    assert "File:" not in answer
    assert "Slide:" not in answer
    assert "Layout:" not in answer
    assert "Slide Blocks:" not in answer
    assert "日本の文化・習慣を理解している人" in answer
    assert "素直な人" in answer