from pathlib import Path

from app.services.document_loaders.image_document_loader import ImageDocumentLoader
from app.services.interfaces.image_understanding_service import ImageAnalysisResult


class _FakeImageUnderstandingService:
    def analyze_image(self, image_bytes: bytes, *, source: str, hint: str) -> ImageAnalysisResult:
        return ImageAnalysisResult(
            text="Detected diagram nodes and relationships.",
            provider="fake-vision",
        )


def test_image_document_loader_returns_analysis_content(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-image-content")

    loader = ImageDocumentLoader(image_understanding_service=_FakeImageUnderstandingService())
    docs = loader.load(image_path)

    assert len(docs) == 1
    assert docs[0].page_content == "Detected diagram nodes and relationships."
    assert docs[0].metadata["extension"] == ".png"
    assert docs[0].metadata["image_analysis_provider"] == "fake-vision"
