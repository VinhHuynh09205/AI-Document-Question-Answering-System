from langchain_core.documents import Document

from app.services.text_chunking_service import TextChunkingService


def test_csv_chunking_emits_row_level_metadata() -> None:
    service = TextChunkingService(chunk_size=400, chunk_overlap=40)
    document = Document(
        page_content="name,score\nAlice,10\nBob,9\n",
        metadata={"source": "scores.csv", "extension": ".csv"},
    )

    chunks = service.split([document])

    assert len(chunks) == 2
    assert chunks[0].metadata["section_title"] == "csv_row"
    assert chunks[0].metadata["row_index"] == 2
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


def test_markdown_chunking_splits_by_headings() -> None:
    service = TextChunkingService(chunk_size=220, chunk_overlap=40)
    document = Document(
        page_content="# Intro\nOverview paragraph\n\n## Detail\nDeep detail paragraph",
        metadata={"source": "guide.md", "extension": ".md"},
    )

    chunks = service.split([document])
    section_titles = {str(chunk.metadata.get("section_title", "")) for chunk in chunks}

    assert "Intro" in section_titles
    assert "Detail" in section_titles