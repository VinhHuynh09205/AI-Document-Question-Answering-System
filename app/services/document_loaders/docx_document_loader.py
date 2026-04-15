from pathlib import Path

from docx import Document as DocxDocument
from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader


class DocxDocumentLoader(IDocumentLoader):
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".docx"

    def load(self, file_path: Path) -> list[Document]:
        doc = DocxDocument(str(file_path))

        paragraph_lines = [
            paragraph.text.strip()
            for paragraph in doc.paragraphs
            if paragraph.text.strip()
        ]

        table_lines: list[str] = []
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    table_lines.append(" | ".join(cells))

        content = "\n".join(paragraph_lines + table_lines)
        return [
            Document(
                page_content=content,
                metadata={"source": str(file_path), "extension": ".docx"},
            )
        ]
