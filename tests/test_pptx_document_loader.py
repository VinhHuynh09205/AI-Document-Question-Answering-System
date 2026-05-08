from app.services.document_loaders.pptx_document_loader import PptxDocumentLoader


def test_pptx_loader_rejects_provider_marker_noise_note() -> None:
    assert (
        PptxDocumentLoader._is_useful_image_note(
            "slide image 1 local_ocr extracted text",
            slide_prefers_cjk=False,
        )
        is False
    )


def test_pptx_loader_rejects_latin_ocr_when_slide_is_cjk() -> None:
    assert (
        PptxDocumentLoader._is_useful_image_note(
            "photpah olibrany ehooln",
            slide_prefers_cjk=True,
        )
        is False
    )


def test_pptx_loader_accepts_meaningful_latin_note() -> None:
    assert (
        PptxDocumentLoader._is_useful_image_note(
            "Customer retention increased by 12 percent year over year.",
            slide_prefers_cjk=False,
        )
        is True
    )


def test_pptx_loader_detects_duplicate_note_from_slide_text() -> None:
    assert (
        PptxDocumentLoader._is_duplicate_image_note(
            "Muc tieu chinh",
            "Muc tieu chinh cua bai hoc la nang cao ky nang.",
            [],
        )
        is True
    )
