import csv
from pathlib import Path

from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader


class CsvDocumentLoader(IDocumentLoader):
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".csv"

    def load(self, file_path: Path) -> list[Document]:
        lines: list[str] = []
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                cells = [cell.strip() for cell in row]
                if any(cells):
                    lines.append(", ".join(cells))

        content = "\n".join(lines)
        return [
            Document(
                page_content=content,
                metadata={"source": str(file_path), "extension": ".csv"},
            )
        ]
