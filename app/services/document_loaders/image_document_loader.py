from pathlib import Path

from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader
from app.services.interfaces.image_understanding_service import IImageUnderstandingService


class ImageDocumentLoader(IDocumentLoader):
    _SUPPORTED_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
        ".gif",
    }

    def __init__(self, image_understanding_service: IImageUnderstandingService | None = None) -> None:
        self._image_understanding_service = image_understanding_service

    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() in self._SUPPORTED_EXTENSIONS

    def load(self, file_path: Path) -> list[Document]:
        image_bytes = file_path.read_bytes()
        extracted = ""
        provider = "not_configured"

        if self._image_understanding_service is not None:
            result = self._image_understanding_service.analyze_image(
                image_bytes,
                source=str(file_path),
                hint="standalone image upload",
            )
            extracted = result.text
            provider = result.provider

        normalized_text = str(extracted or "").strip()
        if not normalized_text:
            normalized_text = "Nội dung hình ảnh chưa rõ."

        return [
            Document(
                page_content=normalized_text,
                metadata={
                    "source": str(file_path),
                    "extension": file_path.suffix.lower(),
                    "image_analysis_provider": provider,
                    "content_type": "image_document",
                    "image_content_unclear": normalized_text == "Nội dung hình ảnh chưa rõ.",
                },
            )
        ]
