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


def test_extract_sources_uses_section_path_for_docx_chunks() -> None:
    docs = [
        Document(
            page_content="Chi tiet noi dung",
            metadata={
                "source": "c:/tmp/guide.docx",
                "section_path": "Introduction > Constraints",
                "chunk_index": 4,
            },
        )
    ]

    sources = QuestionAnsweringService._extract_sources(docs)

    assert sources == ["guide.docx (Introduction > Constraints)"]


def test_extract_sources_uses_sheet_and_range_for_spreadsheet_chunks() -> None:
    docs = [
        Document(
            page_content="Bang du lieu",
            metadata={
                "source": "c:/tmp/data.xlsx",
                "sheet_name": "Finance",
                "range_address": "A1:C18",
                "row_range": "2:8",
            },
        )
    ]

    sources = QuestionAnsweringService._extract_sources(docs)

    assert sources == ["data.xlsx (sheet Finance, A1:C18)"]
