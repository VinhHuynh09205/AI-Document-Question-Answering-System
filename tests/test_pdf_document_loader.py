from app.services.document_loaders.pdf_document_loader import PdfDocumentLoader


class _FakePdfPage:
    def __init__(self, *, layout_text: str, plain_text: str) -> None:
        self._layout_text = layout_text
        self._plain_text = plain_text

    def extract_text(self, *args, extraction_mode: str = "plain", **kwargs) -> str:
        if extraction_mode == "layout":
            return self._layout_text
        return self._plain_text


def test_pdf_loader_prefers_more_readable_layout_text() -> None:
    page = _FakePdfPage(
        layout_text="Ghi lại các phiên bản của PM trong khi test\nSo sánh kết quả thực tế với kết quả mong đợi",
        plain_text="GhilạicácphiênbảncủaPMtrongkhitest\nSosánhkếtquảthựctếvớikếtquảmongđợi",
    )

    extracted = PdfDocumentLoader._extract_page_text(page)

    assert "Ghi lại các phiên bản" in extracted
    assert "So sánh kết quả thực tế" in extracted


def test_pdf_loader_normalizes_blank_lines_without_losing_text() -> None:
    normalized = PdfDocumentLoader._normalize_extracted_text("Dong 1\r\n\r\n\r\nDong 2\u00A0")

    assert normalized == "Dong 1\n\nDong 2"