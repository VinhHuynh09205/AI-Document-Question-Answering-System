from pathlib import Path

from langchain_core.documents import Document
from pptx import Presentation

from app.services.interfaces.document_loader import IDocumentLoader


class PptxDocumentLoader(IDocumentLoader):
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".pptx"

    def load(self, file_path: Path) -> list[Document]:
        prs = Presentation(str(file_path))
        documents: list[Document] = []

        for slide_index, slide in enumerate(prs.slides, start=1):
            parts: list[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        text = paragraph.text.strip()
                        if text:
                            parts.append(text)
                if shape.has_table:
                    for row in shape.table.rows:
                        cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if cells:
                            parts.append(" | ".join(cells))

            content = "\n".join(parts)
            if content.strip():
                documents.append(
                    Document(
                        page_content=content,
                        metadata={
                            "source": str(file_path),
                            "slide": slide_index,
                            "extension": ".pptx",
                        },
                    )
                )

        return documents
