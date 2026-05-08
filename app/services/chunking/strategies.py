from __future__ import annotations

import csv
import io
import re
from abc import ABC, abstractmethod
from itertools import zip_longest

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


_STRUCTURED_EXTENSIONS = {".json", ".xml", ".csv", ".xlsx", ".xls"}
_SECTION_EXTENSIONS = {".doc", ".docx", ".html", ".htm", ".md"}
_SLIDE_EXTENSIONS = {".ppt", ".pptx"}
_PARAGRAPH_EXTENSIONS = {".pdf", ".txt"}


def _normalized_extension(document: Document) -> str:
    return str(document.metadata.get("extension", "")).lower()


def _normalized_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _with_metadata(document: Document, text: str, extra_metadata: dict[str, str | int] | None = None) -> Document:
    metadata = dict(document.metadata)
    if extra_metadata:
        metadata.update(extra_metadata)
    return Document(page_content=_normalized_text(text), metadata=metadata)


def _pack_units(units: list[str], *, chunk_size: int, chunk_overlap: int) -> list[str]:
    compact_units = [_normalized_text(unit) for unit in units if _normalized_text(unit)]
    if not compact_units:
        return []

    chunks: list[str] = []
    current_units: list[str] = []
    current_chars = 0

    for unit in compact_units:
        separator_chars = 1 if current_units else 0
        projected_chars = current_chars + len(unit) + separator_chars

        if current_units and projected_chars > chunk_size:
            chunks.append("\n".join(current_units).strip())

            if chunk_overlap > 0:
                carry_units: list[str] = []
                carry_chars = 0
                for carry_candidate in reversed(current_units):
                    add_chars = len(carry_candidate) + (1 if carry_units else 0)
                    if carry_chars + add_chars > chunk_overlap:
                        break
                    carry_units.insert(0, carry_candidate)
                    carry_chars += add_chars
                current_units = carry_units
                current_chars = sum(len(item) for item in current_units) + max(0, len(current_units) - 1)
            else:
                current_units = []
                current_chars = 0

        current_units.append(unit)
        current_chars += len(unit) + (1 if len(current_units) > 1 else 0)

    if current_units:
        chunks.append("\n".join(current_units).strip())

    return [chunk for chunk in chunks if chunk]


def _split_long_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max(200, chunk_size),
        chunk_overlap=max(0, min(chunk_overlap, chunk_size // 2)),
        add_start_index=False,
    )
    return [part.strip() for part in splitter.split_text(_normalized_text(text)) if part.strip()]


class IChunkingStrategy(ABC):
    @abstractmethod
    def split(
        self,
        document: Document,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[Document]:
        raise NotImplementedError


class StructuredChunkingStrategy(IChunkingStrategy):
    def split(
        self,
        document: Document,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[Document]:
        extension = _normalized_extension(document)

        if extension == ".csv":
            return self._split_csv_rows(document)
        if extension in {".xlsx", ".xls"}:
            return self._split_excel_rows(document)
        if extension in {".json", ".xml"}:
            return self._split_hierarchy(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        text = _normalized_text(document.page_content)
        if not text:
            return []
        return [_with_metadata(document, text)]

    def _split_csv_rows(self, document: Document) -> list[Document]:
        text = _normalized_text(document.page_content)
        if not text:
            return []

        try:
            rows = list(csv.reader(io.StringIO(text), skipinitialspace=True))
        except Exception:
            rows = [[cell.strip() for cell in line.split(",")] for line in text.splitlines() if line.strip()]

        cleaned_rows = [[str(cell).strip() for cell in row] for row in rows if any(str(cell).strip() for cell in row)]
        if not cleaned_rows:
            return []

        header = cleaned_rows[0] if len(cleaned_rows) > 1 else []
        data_rows = cleaned_rows[1:] if header else cleaned_rows
        row_start = 2 if header else 1

        chunks: list[Document] = []
        for offset, row in enumerate(data_rows, start=0):
            row_index = row_start + offset
            if header:
                pairs = [
                    f"{column}: {value}"
                    for column, value in zip_longest(header, row, fillvalue="")
                    if str(column).strip() or str(value).strip()
                ]
                content = "\n".join([f"Row {row_index}", *pairs])
            else:
                content = f"Row {row_index}: " + ", ".join(row)

            chunks.append(
                _with_metadata(
                    document,
                    content,
                    {
                        "section_title": "csv_row",
                        "row_index": row_index,
                    },
                )
            )

        return chunks

    def _split_excel_rows(self, document: Document) -> list[Document]:
        text = _normalized_text(document.page_content)
        if not text:
            return []

        sheet_name = str(document.metadata.get("sheet", "")).strip()
        rows = [line.strip() for line in text.splitlines() if line.strip()]
        if not rows:
            return []

        header = [cell.strip() for cell in rows[0].split("|")] if len(rows) > 1 else []
        data_rows = rows[1:] if header else rows
        row_start = 2 if header else 1

        chunks: list[Document] = []
        for offset, row_line in enumerate(data_rows, start=0):
            row_index = row_start + offset
            values = [cell.strip() for cell in row_line.split("|")]
            if header:
                pairs = [
                    f"{column}: {value}"
                    for column, value in zip_longest(header, values, fillvalue="")
                    if str(column).strip() or str(value).strip()
                ]
                lines = []
                if sheet_name:
                    lines.append(f"Sheet: {sheet_name}")
                lines.append(f"Row {row_index}")
                lines.extend(pairs)
                content = "\n".join(lines)
            else:
                prefix = f"Sheet: {sheet_name}\n" if sheet_name else ""
                content = f"{prefix}Row {row_index}: {row_line}".strip()

            chunks.append(
                _with_metadata(
                    document,
                    content,
                    {
                        "sheet_name": sheet_name,
                        "section_title": "excel_row",
                        "row_index": row_index,
                    },
                )
            )

        return chunks

    def _split_hierarchy(self, document: Document, *, chunk_size: int, chunk_overlap: int) -> list[Document]:
        text = _normalized_text(document.page_content)
        if not text:
            return []

        grouped: dict[str, list[str]] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            path = line.split(":", 1)[0]
            top_level = path.split(".", 1)[0].split("[", 1)[0].strip() or "root"
            grouped.setdefault(top_level, []).append(line)

        chunks: list[Document] = []
        for top_level, lines in grouped.items():
            packed = _pack_units(lines, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            if not packed:
                continue
            for chunk_text in packed:
                chunks.append(
                    _with_metadata(
                        document,
                        chunk_text,
                        {
                            "section_title": top_level,
                        },
                    )
                )

        return chunks


class SectionBasedChunkingStrategy(IChunkingStrategy):
    _MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")

    def split(
        self,
        document: Document,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[Document]:
        text = _normalized_text(document.page_content)
        if not text:
            return []

        extension = _normalized_extension(document)
        sections = self._extract_sections(text, extension=extension)
        if not sections:
            return [_with_metadata(document, text)]

        chunks: list[Document] = []
        for section_title, section_content in sections:
            compact_content = _normalized_text(section_content)
            if not compact_content:
                continue

            if len(compact_content) <= chunk_size:
                chunks.append(
                    _with_metadata(
                        document,
                        compact_content,
                        {"section_title": section_title},
                    )
                )
                continue

            for piece in _split_long_text(compact_content, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
                chunks.append(
                    _with_metadata(
                        document,
                        piece,
                        {"section_title": section_title},
                    )
                )

        return chunks

    def _extract_sections(self, text: str, *, extension: str) -> list[tuple[str, str]]:
        lines = text.splitlines()
        sections: list[tuple[str, str]] = []

        current_title = "overview"
        current_lines: list[str] = []
        in_code_block = False

        def _flush() -> None:
            nonlocal current_lines
            content = _normalized_text("\n".join(current_lines))
            if content:
                sections.append((current_title, content))
            current_lines = []

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()

            if extension == ".md" and stripped.startswith("```"):
                in_code_block = not in_code_block
                current_lines.append(line)
                continue

            heading_title = ""
            markdown_match = self._MARKDOWN_HEADING_RE.match(line)
            if markdown_match and not in_code_block:
                heading_title = markdown_match.group(1).strip()
            elif not in_code_block and self._looks_like_section_heading(stripped):
                heading_title = stripped

            if heading_title:
                _flush()
                current_title = heading_title[:120]
                continue

            current_lines.append(line)

        _flush()
        return sections

    @staticmethod
    def _looks_like_section_heading(line: str) -> bool:
        if not line:
            return False
        if len(line) > 120:
            return False
        if line.endswith(":") and len(line.split()) <= 12:
            return True
        if line.isupper() and len(line.split()) <= 10:
            return True
        if re.match(r"^\d+(?:\.\d+){0,3}\s+", line):
            return True
        return False


class SlideBasedChunkingStrategy(IChunkingStrategy):
    def split(
        self,
        document: Document,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[Document]:
        text = _normalized_text(document.page_content)
        if not text:
            return []

        slide_number = int(document.metadata.get("slide", 0) or 0)
        slide_title = self._extract_slide_title(text)
        paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
        packed = _pack_units(paragraphs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        if not packed:
            packed = _split_long_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        chunks: list[Document] = []
        for chunk_text in packed:
            chunks.append(
                _with_metadata(
                    document,
                    chunk_text,
                    {
                        "section_title": slide_title,
                        "slide_number": slide_number,
                    },
                )
            )

        return chunks

    @staticmethod
    def _extract_slide_title(text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if len(stripped) <= 120:
                return stripped
            return stripped[:117].rstrip() + "..."
        return "slide"


class ParagraphBasedChunkingStrategy(IChunkingStrategy):
    def split(
        self,
        document: Document,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[Document]:
        text = _normalized_text(document.page_content)
        if not text:
            return []

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
        if not paragraphs:
            paragraphs = [line.strip() for line in text.splitlines() if line.strip()]

        packed = _pack_units(paragraphs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not packed:
            packed = _split_long_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        chunks: list[Document] = []
        for chunk_text in packed:
            section_title = self._detect_section_title(chunk_text)
            chunks.append(
                _with_metadata(
                    document,
                    chunk_text,
                    {"section_title": section_title},
                )
            )

        return chunks

    @staticmethod
    def _detect_section_title(chunk_text: str) -> str:
        first_line = str(chunk_text or "").splitlines()[0].strip() if chunk_text else ""
        if not first_line:
            return "paragraph"

        if len(first_line) <= 100 and (
            first_line.endswith(":")
            or re.match(r"^\d+(?:\.\d+){0,3}\s+", first_line)
            or first_line.isupper()
        ):
            return first_line[:120]

        words = first_line.split()
        if len(words) <= 10:
            return first_line[:120]

        return "paragraph"


class ChunkingStrategyFactory:
    def __init__(self) -> None:
        self._structured = StructuredChunkingStrategy()
        self._section = SectionBasedChunkingStrategy()
        self._slide = SlideBasedChunkingStrategy()
        self._paragraph = ParagraphBasedChunkingStrategy()

    def resolve(self, document: Document) -> IChunkingStrategy:
        extension = _normalized_extension(document)
        if extension in _STRUCTURED_EXTENSIONS:
            return self._structured
        if extension in _SECTION_EXTENSIONS:
            return self._section
        if extension in _SLIDE_EXTENSIONS:
            return self._slide
        if extension in _PARAGRAPH_EXTENSIONS:
            return self._paragraph
        return self._paragraph
