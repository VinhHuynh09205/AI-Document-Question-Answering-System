import time

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


def test_pptx_loader_accepts_numeric_chart_note_without_two_latin_words() -> None:
    assert (
        PptxDocumentLoader._is_useful_image_note(
            "trieungoi 26.9 24.2 22.3 20.8",
            slide_prefers_cjk=False,
        )
        is True
    )


def test_pptx_loader_skips_dense_text_slide_with_single_picture() -> None:
    loader = PptxDocumentLoader(
        image_understanding_service=object(),
        text_char_threshold_for_image_analysis=900,
    )

    should_analyze = loader._should_analyze_slide_images(
        text_snapshot="word " * 220,
        total_images_analyzed=0,
        analyzed_slides=0,
        started_at=time.perf_counter(),
        picture_count=1,
    )

    assert should_analyze is False


def test_pptx_loader_allows_image_heavy_slide_with_limited_text() -> None:
    loader = PptxDocumentLoader(
        image_understanding_service=object(),
        text_char_threshold_for_image_analysis=900,
    )

    should_analyze = loader._should_analyze_slide_images(
        text_snapshot="Key chart summary",
        total_images_analyzed=0,
        analyzed_slides=0,
        started_at=time.perf_counter(),
        picture_count=3,
    )

    assert should_analyze is True


def test_pptx_loader_honors_max_slides_with_image_analysis() -> None:
    loader = PptxDocumentLoader(
        image_understanding_service=object(),
        max_slides_with_image_analysis=2,
    )

    should_analyze = loader._should_analyze_slide_images(
        text_snapshot="small text",
        total_images_analyzed=0,
        analyzed_slides=2,
        started_at=time.perf_counter(),
        picture_count=2,
    )

    assert should_analyze is False
