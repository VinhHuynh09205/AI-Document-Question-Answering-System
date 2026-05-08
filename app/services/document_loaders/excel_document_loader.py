from pathlib import Path
import re

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
            raw_rows: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(cell).strip() for cell in row if cell is not None]
                if cells:
                    raw_rows.append(cells)

            lines = [" | ".join(cells) for cells in raw_rows]

            content = "\n".join(lines)
            if content.strip():
                header = raw_rows[0] if len(raw_rows) > 1 else []
                has_header = self._looks_like_header(header)
                data_rows = raw_rows[1:] if has_header else raw_rows
                numeric_columns, categorical_columns = self._infer_column_types(
                    header=header,
                    data_rows=data_rows,
                )

                documents.append(
                    Document(
                        page_content=content,
                        metadata={
                            "source": str(file_path),
                            "sheet": sheet_name,
                            "extension": file_path.suffix.lower(),
                            "content_type": "spreadsheet_sheet",
                            "row_count": len(data_rows),
                            "column_count": max((len(cells) for cells in raw_rows), default=0),
                            "has_header": has_header,
                            "numeric_columns": numeric_columns,
                            "categorical_columns": categorical_columns,
                        },
                    )
                )

        wb.close()
        return documents

    @staticmethod
    def _looks_like_header(header: list[str]) -> bool:
        if not header:
            return False

        non_empty = [cell for cell in header if str(cell).strip()]
        if not non_empty:
            return False

        numeric_like = 0
        for cell in non_empty:
            normalized = str(cell).strip()
            if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", normalized):
                numeric_like += 1

        return numeric_like < len(non_empty)

    @staticmethod
    def _infer_column_types(
        *,
        header: list[str],
        data_rows: list[list[str]],
    ) -> tuple[list[str], list[str]]:
        if not data_rows:
            return [], []

        max_columns = max((len(row) for row in data_rows), default=len(header))
        numeric_columns: list[str] = []
        categorical_columns: list[str] = []

        for column_index in range(max_columns):
            column_name = (
                str(header[column_index]).strip()
                if column_index < len(header) and str(header[column_index]).strip()
                else f"column_{column_index + 1}"
            )

            values = [
                str(row[column_index]).strip()
                for row in data_rows
                if column_index < len(row) and str(row[column_index]).strip()
            ]
            if not values:
                continue

            numeric_count = sum(
                1 for value in values
                if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", value)
            )
            ratio = numeric_count / max(1, len(values))
            if ratio >= 0.8:
                numeric_columns.append(column_name)
            else:
                categorical_columns.append(column_name)

        return numeric_columns, categorical_columns
