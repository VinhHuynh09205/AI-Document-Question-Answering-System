from langchain_core.documents import Document

from app.services.text_chunking_service import TextChunkingService


def test_xlsx_chunking_emits_row_level_metadata() -> None:
    service = TextChunkingService(chunk_size=400, chunk_overlap=40)
    document = Document(
        page_content="name|score\nAlice|10\nBob|9\n",
        metadata={"source": "scores.xlsx", "extension": ".xlsx", "sheet": "Sheet1"},
    )

    chunks = service.split([document])

    assert len(chunks) == 2
    assert chunks[0].metadata["section_title"] == "excel_row"
    assert chunks[0].metadata["row_index"] == 2
    assert chunks[0].metadata["sheet_name"] == "Sheet1"
    assert chunks[0].metadata["structure_path"] == "Sheet: Sheet1 > Row: 2"
    assert chunks[0].metadata["chunk_profile"] == "structured"
    assert chunks[0].metadata["chunk_quality_band"] in {"medium", "high"}
    assert "name: Alice" in chunks[0].page_content


def test_slide_chunking_preserves_slide_metadata() -> None:
    service = TextChunkingService(chunk_size=220, chunk_overlap=40)
    document = Document(
        page_content="Quarterly Plan\nObjective one\nObjective two\n",
        metadata={"source": "deck.pptx", "extension": ".pptx", "slide": 3},
    )

    chunks = service.split([document])

    assert chunks
    assert chunks[0].metadata["slide_number"] == 3
    assert chunks[0].metadata["section_title"] == "Quarterly Plan"
    assert chunks[0].metadata["structure_path"] == "Slide: 3 > Quarterly Plan"
    assert chunks[0].metadata["chunk_profile"] == "slide"


def test_markdown_chunking_splits_by_headings() -> None:
    service = TextChunkingService(chunk_size=220, chunk_overlap=40)
    document = Document(
        page_content="# Intro\nOverview paragraph\n\n## Detail\nDeep detail paragraph",
        metadata={"source": "guide.md", "extension": ".md"},
    )

    chunks = service.split([document])
    section_titles = {str(chunk.metadata.get("section_title", "")) for chunk in chunks}
    section_paths = {str(chunk.metadata.get("section_path", "")) for chunk in chunks}

    assert "Intro" in section_titles
    assert "Detail" in section_titles
    assert "Intro" in section_paths
    assert "Intro > Detail" in section_paths


def test_structured_excel_table_chunking_keeps_sheet_range_headers() -> None:
    service = TextChunkingService(chunk_size=260, chunk_overlap=40)
    rows = []
    for row_number in range(2, 9):
        rows.append(
            {
                "row_number": row_number,
                "row_range": f"A{row_number}:C{row_number}",
                "values": {
                    "Code": f"P{row_number:03d}",
                    "Revenue": str(100 + row_number),
                    "Month": "2026-01",
                },
                "cells": [
                    {"address": f"A{row_number}", "header": "Code", "value": f"P{row_number:03d}"},
                    {"address": f"B{row_number}", "header": "Revenue", "value": str(100 + row_number)},
                    {"address": f"C{row_number}", "header": "Month", "value": "2026-01"},
                ],
            }
        )

    document = Document(
        page_content="Spreadsheet table",
        metadata={
            "source": "finance.xlsx",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table",
            "sheet_name": "Finance",
            "table_name": "used_range_1",
            "range_address": "A1:C8",
            "headers": ["Code", "Revenue", "Month"],
            "structured_rows": rows,
        },
    )

    chunks = service.split([document])

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.metadata["content_type"] == "spreadsheet_table_chunk"
        assert chunk.metadata["sheet_name"] == "Finance"
        assert chunk.metadata["range_address"] == "A1:C8"
        assert chunk.metadata["headers"] == ["Code", "Revenue", "Month"]
        assert chunk.metadata["chunk_profile"] == "structured"
        assert chunk.metadata["table_id"] == "Finance::used_range_1::A1:C8"
        assert "Sheet: Finance > Table: used_range_1 > Rows:" in chunk.metadata["structure_path"]
        assert "Sheet: Finance" in chunk.page_content
        assert "Range: A1:C8" in chunk.page_content


def test_structured_slide_chunking_keeps_slide_block_metadata() -> None:
    service = TextChunkingService(chunk_size=250, chunk_overlap=40)
    blocks = [
        {
            "reading_order": 1,
            "block_type": "textbox",
            "object_type": "text_box",
            "position": "x=0,y=0,w=100,h=20",
            "content": "Executive summary with key goals and constraints for deployment.",
        },
        {
            "reading_order": 2,
            "block_type": "table",
            "object_type": "graphic_frame",
            "position": "x=0,y=30,w=100,h=40",
            "content": "Q1 | 120\nQ2 | 150\nQ3 | 190",
        },
        {
            "reading_order": 3,
            "block_type": "chart",
            "object_type": "chart",
            "position": "x=0,y=80,w=100,h=40",
            "content": "Trend increased steadily after June.",
        },
        {
            "reading_order": 4,
            "block_type": "speaker_notes",
            "object_type": "notes",
            "position": "",
            "content": "Remind stakeholders that variance is due to promotions.",
        },
    ]

    document = Document(
        page_content="Slide structured content",
        metadata={
            "source": "deck.pptx",
            "extension": ".pptx",
            "content_type": "slide_structured",
            "slide_number": 4,
            "slide_title": "Quarterly Review",
            "slide_layout": "Title and Content",
            "slide_blocks": blocks,
        },
    )

    chunks = service.split([document])

    assert chunks
    for chunk in chunks:
        assert chunk.metadata["slide_number"] == 4
        assert chunk.metadata["section_title"] == "Quarterly Review"
        assert isinstance(chunk.metadata.get("block_types"), list)
        assert chunk.metadata["chunk_profile"] == "slide"
        assert chunk.metadata["structure_path"].startswith("Slide: 4 > Quarterly Review > Blocks:")
        assert "Slide: 4" in chunk.page_content
        assert "Title: Quarterly Review" in chunk.page_content