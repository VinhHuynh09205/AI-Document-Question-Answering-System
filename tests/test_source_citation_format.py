from langchain_core.documents import Document

from app.services.question_answering_service import QuestionAnsweringService


def test_extract_sources_prefers_page_and_ignores_chunk_index() -> None:
    docs = [
        Document(
            page_content="Du lieu mau",
            metadata={
                "source": "c:/tmp/1234567890abcdef1234567890abcdef_AIDocument.docx",
                "page": 12,
                "chunk_index": 86,
            },
        )
    ]

    sources = QuestionAnsweringService._extract_sources(docs)

    assert sources == ["AIDocument.docx (trang 12)"]


def test_extract_sources_falls_back_to_slide_when_page_missing() -> None:
    docs = [
        Document(
            page_content="Slide noi dung",
            metadata={
                "source": "c:/tmp/demo.pptx",
                "slide_number": 3,
                "chunk_index": 9,
            },
        )
    ]

    sources = QuestionAnsweringService._extract_sources(docs)

    assert sources == ["demo.pptx (slide 3)"]


def test_extract_sources_does_not_show_chunk_index_when_page_missing() -> None:
    docs = [
        Document(
            page_content="Noi dung",
            metadata={
                "source": "c:/tmp/report.docx",
                "chunk_index": 86,
            },
        )
    ]

    sources = QuestionAnsweringService._extract_sources(docs)

    assert sources == ["report.docx"]
