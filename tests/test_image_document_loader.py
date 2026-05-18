from pathlib import Path

from app.services.document_loaders.image_document_loader import ImageDocumentLoader
from app.services.interfaces.image_understanding_service import ImageAnalysisResult


class _FakeImageUnderstandingService:
    def __init__(self) -> None:
        self.preserve_flags: list[bool] = []

    def analyze_image(
        self,
        image_bytes: bytes,
        *,
        source: str,
        hint: str,
        preserve_full_text: bool = False,
    ) -> ImageAnalysisResult:
        self.preserve_flags.append(preserve_full_text)
        return ImageAnalysisResult(
            text="Detected diagram nodes and relationships.",
            provider="fake-vision",
        )


def test_image_document_loader_returns_analysis_content(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-image-content")

    fake_service = _FakeImageUnderstandingService()
    loader = ImageDocumentLoader(image_understanding_service=fake_service)
    docs = loader.load(image_path)

    assert len(docs) == 1
    assert "File: sample.png" in docs[0].page_content
    assert "OCR Text:" in docs[0].page_content
    assert "Vision Description:" in docs[0].page_content
    assert "Detected diagram nodes and relationships." in docs[0].page_content
    assert docs[0].metadata["extension"] == ".png"
    assert docs[0].metadata["image_analysis_provider"] == "fake-vision"
    assert docs[0].metadata["image_analysis_applied"] is True
    assert fake_service.preserve_flags == [True]
