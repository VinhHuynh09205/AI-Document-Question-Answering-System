from pathlib import Path

from langchain_core.documents import Document
from pypdf import PdfReader

from app.services.interfaces.document_loader import IDocumentLoader


class PdfDocumentLoader(IDocumentLoader):
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".pdf"

    def load(self, file_path: Path) -> list[Document]:
        reader = PdfReader(str(file_path))
        documents: list[Document] = []

        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": str(file_path),
                        "page": index,
                        "extension": ".pdf",
                    },
                )
            )

        return documents
