import csv
import io
import re
from pathlib import Path

from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader
from app.utils.text_io import read_text_with_fallback


class CsvDocumentLoader(IDocumentLoader):
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".csv"

    def load(self, file_path: Path) -> list[Document]:
        raw_text = read_text_with_fallback(file_path)
        reader = csv.reader(io.StringIO(raw_text), skipinitialspace=True)

        rows: list[list[str]] = []
        for row in reader:
            cells = [str(cell).strip() for cell in row]
            if any(cells):
                rows.append(cells)

        if not rows:
            return [
                Document(
                    page_content="",
                    metadata={
                        "source": str(file_path),
                        "extension": ".csv",
                        "content_type": "csv_table",
                        "row_count": 0,
                        "column_count": 0,
                    },
                )
            ]

        header = rows[0] if len(rows) > 1 else []
        has_header = self._looks_like_header(header)
        data_rows = rows[1:] if has_header else rows

        lines: list[str] = [", ".join(row) for row in rows]

        numeric_columns, categorical_columns = self._infer_column_types(
            header=header,
            data_rows=data_rows,
        )

        content = "\n".join(lines)
        return [
            Document(
                page_content=content,
                metadata={
                    "source": str(file_path),
                    "extension": ".csv",
                    "content_type": "csv_table",
                    "row_count": len(data_rows),
                    "column_count": max((len(row) for row in rows), default=0),
                    "has_header": has_header,
                    "numeric_columns": numeric_columns,
                    "categorical_columns": categorical_columns,
                },
            )
        ]

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
