from pathlib import Path

from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader
from app.utils.text_io import read_text_with_fallback


class TextDocumentLoader(IDocumentLoader):
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".txt"

    def load(self, file_path: Path) -> list[Document]:
        content = read_text_with_fallback(file_path)
        return [
            Document(
                page_content=content,
                metadata={"source": str(file_path), "extension": ".txt"},
            )
        ]
