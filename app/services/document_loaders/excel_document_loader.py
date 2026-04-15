from pathlib import Path

from langchain_core.documents import Document
from openpyxl import load_workbook

from app.services.interfaces.document_loader import IDocumentLoader


class ExcelDocumentLoader(IDocumentLoader):
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() in (".xlsx", ".xls")

    def load(self, file_path: Path) -> list[Document]:
        wb = load_workbook(str(file_path), read_only=True, data_only=True)
        documents: list[Document] = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            lines: list[str] = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(cell).strip() for cell in row if cell is not None]
                if cells:
                    lines.append(" | ".join(cells))

            content = "\n".join(lines)
            if content.strip():
                documents.append(
                    Document(
                        page_content=content,
                        metadata={
                            "source": str(file_path),
                            "sheet": sheet_name,
                            "extension": file_path.suffix.lower(),
                        },
                    )
                )

        wb.close()
        return documents
