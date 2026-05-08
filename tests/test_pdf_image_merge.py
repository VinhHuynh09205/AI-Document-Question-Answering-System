from app.services.document_loaders.pdf_document_loader import PdfDocumentLoader


def test_pdf_merge_text_and_image_notes_keeps_both_sections() -> None:
    merged = PdfDocumentLoader._merge_text_and_image_notes(
        text="Existing page text.",
        image_notes=["[Image 1 | gemini] Extracted flowchart details."],
    )

    assert "Existing page text." in merged
    assert "[Image insights]" in merged
    assert "Extracted flowchart details." in merged
