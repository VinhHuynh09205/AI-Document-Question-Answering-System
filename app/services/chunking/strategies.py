from __future__ import annotations

import re
from abc import ABC, abstractmethod
from itertools import zip_longest

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


_STRUCTURED_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}
_SECTION_EXTENSIONS = {".docx", ".md"}
_SLIDE_EXTENSIONS = {".ppt", ".pptx"}
_PARAGRAPH_EXTENSIONS = {".pdf", ".txt"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def _compose_structure_path(*parts: str | int | None) -> str:
    normalized_parts: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if not text:
            continue
        normalized_parts.append(text)
    return " > ".join(normalized_parts)


def _normalized_extension(document: Document) -> str:
    return str(document.metadata.get("extension", "")).lower()


def _normalized_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _with_metadata(
    document: Document,
    text: str,
    extra_metadata: dict[str, str | int | bool | list | dict] | None = None,
    exclude_metadata_keys: set[str] | None = None,
) -> Document:
    metadata = dict(document.metadata)
    if exclude_metadata_keys:
        for key in exclude_metadata_keys:
            metadata.pop(key, None)
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
        content_type = str(document.metadata.get("content_type", "")).strip().lower()

        if extension in {".xlsx", ".xls", ".xlsm"}:
            if content_type == "spreadsheet_table":
                return self._split_structured_excel_table(
                    document,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            return self._split_excel_rows(document)

        text = _normalized_text(document.page_content)
        if not text:
            return []
        return [_with_metadata(document, text)]

    def _split_structured_excel_table(
        self,
        document: Document,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[Document]:
        rows_raw = document.metadata.get("structured_rows")
        rows: list[dict[str, object]] = rows_raw if isinstance(rows_raw, list) else []
        if not rows:
            text = _normalized_text(document.page_content)
            if not text:
                return []
            return [
                _with_metadata(
                    document,
                    text,
                    {"content_type": "spreadsheet_table_chunk"},
                    exclude_metadata_keys={"structured_rows"},
                )
            ]

        row_units: list[tuple[dict[str, object], str]] = []
        for row in rows:
            row_text = self._format_excel_row_line(row)
            if not row_text:
                continue
            row_units.append((row, row_text))

        if not row_units:
            return []

        groups: list[list[tuple[dict[str, object], str]]] = []
        current_group: list[tuple[dict[str, object], str]] = []
        current_chars = 0
        effective_limit = max(420, chunk_size - 280)

        for unit in row_units:
            projected = current_chars + len(unit[1]) + (1 if current_group else 0)
            if current_group and projected > effective_limit:
                groups.append(current_group)

                if chunk_overlap > 0:
                    carry: list[tuple[dict[str, object], str]] = []
                    carry_chars = 0
                    for candidate in reversed(current_group):
                        candidate_chars = len(candidate[1]) + (1 if carry else 0)
                        if carry_chars + candidate_chars > chunk_overlap:
                            break
                        carry.insert(0, candidate)
                        carry_chars += candidate_chars
                    current_group = carry
                    current_chars = sum(len(item[1]) for item in current_group) + max(0, len(current_group) - 1)
                else:
                    current_group = []
                    current_chars = 0

            current_group.append(unit)
            current_chars += len(unit[1]) + (1 if len(current_group) > 1 else 0)

        if current_group:
            groups.append(current_group)

        chunks: list[Document] = []
        for group in groups:
            group_rows = [row for row, _ in group]
            group_lines = [line for _, line in group]
            content = self._build_excel_chunk_text(document, group_lines, group_rows)
            if not content:
                continue

            row_start = int(group_rows[0].get("row_number", 0) or 0)
            row_end = int(group_rows[-1].get("row_number", 0) or 0)
            headers = list(document.metadata.get("headers") or [])

            chunks.append(
                _with_metadata(
                    document,
                    content,
                    {
                        "content_type": "spreadsheet_table_chunk",
                        "sheet_name": str(document.metadata.get("sheet_name") or document.metadata.get("sheet") or ""),
                        "table_name": str(document.metadata.get("table_name") or "used_range_1"),
                        "range_address": str(document.metadata.get("range_address") or ""),
                        "row_range": f"{row_start}:{row_end}",
                        "row_start": row_start,
                        "row_end": row_end,
                        "table_id": "::".join(
                            part
                            for part in (
                                str(document.metadata.get("sheet_name") or document.metadata.get("sheet") or "").strip(),
                                str(document.metadata.get("table_name") or "used_range_1").strip(),
                                str(document.metadata.get("range_address") or "").strip(),
                            )
                            if part
                        ),
                        "table_chunk_position": {
                            "row_start": row_start,
                            "row_end": row_end,
                        },
                        "headers": headers,
                        "structured_rows": group_rows,
                        "block_type": "table_range",
                        "section_title": str(document.metadata.get("section_title") or document.metadata.get("sheet_name") or "spreadsheet"),
                        "structure_path": _compose_structure_path(
                            (
                                f"Sheet: {str(document.metadata.get('sheet_name') or document.metadata.get('sheet') or '').strip()}"
                                if str(document.metadata.get("sheet_name") or document.metadata.get("sheet") or "").strip()
                                else "Spreadsheet"
                            ),
                            f"Table: {str(document.metadata.get('table_name') or 'used_range_1').strip()}",
                            f"Rows: {row_start}-{row_end}",
                        ),
                    },
                    exclude_metadata_keys={"structured_rows"},
                )
            )

        return chunks

    def _build_excel_chunk_text(
        self,
        document: Document,
        row_lines: list[str],
        rows: list[dict[str, object]],
    ) -> str:
        if not row_lines or not rows:
            return ""

        file_name = str(document.metadata.get("file_name") or document.metadata.get("document_name") or "")
        sheet_name = str(document.metadata.get("sheet_name") or document.metadata.get("sheet") or "")
        sheet_index = document.metadata.get("sheet_index")
        sheet_hidden = bool(document.metadata.get("sheet_hidden"))
        table_name = str(document.metadata.get("table_name") or "used_range_1")
        table_kind = str(document.metadata.get("table_kind") or "used_range")
        range_address = str(document.metadata.get("range_address") or "")
        headers = list(document.metadata.get("headers") or [])
        header_units = document.metadata.get("header_units") or {}

        row_start = int(rows[0].get("row_number", 0) or 0)
        row_end = int(rows[-1].get("row_number", 0) or 0)

        header_line = ", ".join(str(item).strip() for item in headers if str(item).strip()) or "(none)"
        unit_line = ", ".join(
            f"{header}={value}"
            for header, value in (header_units.items() if isinstance(header_units, dict) else [])
            if str(value).strip()
        ) or "(none)"

        lines = [
            f"File: {file_name}" if file_name else "File: unknown",
            f"Sheet: {sheet_name}",
            f"Sheet Index: {sheet_index}" if sheet_index is not None else "",
            f"Hidden Sheet: {sheet_hidden}",
            f"Table: {table_name}",
            f"Table Type: {table_kind}",
            f"Range: {range_address}",
            f"Chunk Row Range: {row_start}:{row_end}",
            f"Headers: {header_line}",
            f"Header Units: {unit_line}",
            "Structured Rows:",
        ]

        lines.extend(f"- {line}" for line in row_lines)
        return _normalized_text("\n".join(line for line in lines if line is not None))

    @staticmethod
    def _format_excel_row_line(row: dict[str, object]) -> str:
        row_number = int(row.get("row_number", 0) or 0)
        row_range = str(row.get("row_range") or "")
        cells_raw = row.get("cells")
        cells = cells_raw if isinstance(cells_raw, list) else []

        fragments: list[str] = []
        for cell in cells:
            if not isinstance(cell, dict):
                continue

            header = str(cell.get("header") or "").strip()
            address = str(cell.get("address") or "").strip()
            value = str(cell.get("value") or "").strip()
            formula = str(cell.get("formula") or "").strip()
            comment = str(cell.get("comment") or "").strip()
            hyperlink = str(cell.get("hyperlink") or "").strip()
            merged_range = str(cell.get("merged_range") or "").strip()

            if not any([value, formula, comment, hyperlink]):
                continue

            label = header or address or "cell"
            details = value if value else ""
            if formula:
                details = f"{details} [formula={formula}]".strip()
            if comment:
                details = f"{details} [comment={comment}]".strip()
            if hyperlink:
                details = f"{details} [link={hyperlink}]".strip()
            if merged_range:
                details = f"{details} [merged={merged_range}]".strip()

            location = f" ({address})" if address else ""
            fragments.append(f"{label}{location}: {details}".strip())

        if not fragments:
            values = row.get("values")
            if isinstance(values, dict):
                for key, value in values.items():
                    value_text = str(value).strip()
                    if not value_text:
                        continue
                    fragments.append(f"{key}: {value_text}")

        if not fragments:
            return ""

        return f"Row {row_number} [{row_range}]: {'; '.join(fragments)}"

    def _split_excel_rows(self, document: Document) -> list[Document]:
        text = _normalized_text(document.page_content)
        if not text:
            return []

        content_type = str(document.metadata.get("content_type", "")).strip().lower()
        if content_type in {"spreadsheet_row", "spreadsheet_sheet", "spreadsheet_sheet_summary"}:
            extra_metadata: dict[str, str | int] = {}
            sheet_name = str(document.metadata.get("sheet_name") or document.metadata.get("sheet") or "").strip()
            if sheet_name:
                extra_metadata["sheet_name"] = sheet_name
                if content_type in {"spreadsheet_sheet", "spreadsheet_sheet_summary"}:
                    extra_metadata["section_title"] = sheet_name
            return [_with_metadata(document, text, extra_metadata)]

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
                        "structure_path": _compose_structure_path(
                            f"Sheet: {sheet_name}" if sheet_name else "Spreadsheet",
                            f"Row: {row_index}",
                        ),
                    },
                )
            )

        return chunks



class SectionBasedChunkingStrategy(IChunkingStrategy):
    _MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")

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
        for section in sections:
            section_title = str(section["section_title"])
            section_content = str(section["content"])
            section_path = str(section["section_path"])
            heading_level = int(section["heading_level"])
            compact_content = _normalized_text(section_content)
            if not compact_content:
                continue

            if len(compact_content) <= chunk_size:
                chunks.append(
                    _with_metadata(
                        document,
                        compact_content,
                        {
                            "section_title": section_title,
                            "section_path": section_path,
                            "structure_path": section_path,
                            "heading_level": heading_level,
                        },
                    )
                )
                continue

            for piece in _split_long_text(compact_content, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
                chunks.append(
                    _with_metadata(
                        document,
                        piece,
                        {
                            "section_title": section_title,
                            "section_path": section_path,
                            "structure_path": section_path,
                            "heading_level": heading_level,
                        },
                    )
                )

        return chunks

    def _extract_sections(self, text: str, *, extension: str) -> list[dict[str, str | int]]:
        lines = text.splitlines()
        sections: list[dict[str, str | int]] = []

        current_title = "overview"
        current_path = "overview"
        current_level = 0
        current_lines: list[str] = []
        in_code_block = False
        heading_stack: list[tuple[int, str]] = []

        def _flush() -> None:
            nonlocal current_lines
            content = _normalized_text("\n".join(current_lines))
            if content:
                sections.append(
                    {
                        "section_title": current_title,
                        "content": content,
                        "section_path": current_path,
                        "heading_level": current_level,
                    }
                )
            current_lines = []

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()

            if extension == ".md" and stripped.startswith("```"):
                in_code_block = not in_code_block
                current_lines.append(line)
                continue

            heading_title = ""
            heading_level = 0
            markdown_match = self._MARKDOWN_HEADING_RE.match(line)
            if markdown_match and not in_code_block:
                heading_level = len(markdown_match.group(1))
                heading_title = markdown_match.group(2).strip()
            elif not in_code_block and self._looks_like_section_heading(stripped):
                heading_title = stripped
                heading_level = self._infer_heuristic_heading_level(stripped)

            if heading_title:
                _flush()
                current_title = heading_title[:120]
                current_level = heading_level

                while heading_stack and heading_stack[-1][0] >= heading_level:
                    heading_stack.pop()
                heading_stack.append((heading_level, current_title))
                current_path = _compose_structure_path(*(title for _, title in heading_stack)) or current_title
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

    @staticmethod
    def _infer_heuristic_heading_level(line: str) -> int:
        numbered_match = re.match(r"^(\d+(?:\.\d+){0,3})\s+", line)
        if numbered_match:
            return min(6, numbered_match.group(1).count(".") + 1)
        return 1


class SlideBasedChunkingStrategy(IChunkingStrategy):
    def split(
        self,
        document: Document,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[Document]:
        blocks_raw = document.metadata.get("slide_blocks")
        if isinstance(blocks_raw, list) and blocks_raw:
            return self._split_structured_slide(
                document,
                blocks=blocks_raw,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

        text = _normalized_text(document.page_content)
        if not text:
            return []

        slide_number = int(document.metadata.get("slide_number") or document.metadata.get("slide", 0) or 0)
        slide_title = str(document.metadata.get("slide_title") or "").strip() or self._extract_slide_title(text)
        paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
        packed = _pack_units(paragraphs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        if not packed:
            packed = _split_long_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        chunks: list[Document] = []
        for chunk_text in packed:
            structure_path = _compose_structure_path(
                f"Slide: {slide_number}" if slide_number > 0 else "Slide",
                slide_title,
            )
            chunks.append(
                _with_metadata(
                    document,
                    chunk_text,
                    {
                        "section_title": slide_title,
                        "slide_number": slide_number,
                        "structure_path": structure_path,
                    },
                )
            )

        return chunks

    def _split_structured_slide(
        self,
        document: Document,
        *,
        blocks: list[dict],
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[Document]:
        block_units: list[tuple[dict, str]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue

            text = self._format_block_text(block)
            if not text:
                continue
            block_units.append((block, text))

        if not block_units:
            text = _normalized_text(document.page_content)
            return [_with_metadata(document, text)] if text else []

        joined_length = sum(len(item[1]) for item in block_units)
        if len(block_units) <= 10 and joined_length <= max(480, chunk_size - 220):
            groups = [block_units]
        else:
            groups = self._pack_blocks(
                block_units,
                chunk_size=max(420, chunk_size - 260),
                chunk_overlap=chunk_overlap,
            )

        slide_number = int(document.metadata.get("slide_number") or document.metadata.get("slide", 0) or 0)
        slide_title = str(document.metadata.get("slide_title") or "").strip() or f"Slide {slide_number}"
        slide_layout = str(document.metadata.get("slide_layout") or "").strip()

        chunks: list[Document] = []
        for group in groups:
            group_blocks = [item[0] for item in group]
            group_lines = [item[1] for item in group]

            reading_orders = [
                int(block.get("reading_order", 0) or 0)
                for block in group_blocks
                if int(block.get("reading_order", 0) or 0) > 0
            ]
            block_types = [
                str(block.get("block_type") or "").strip()
                for block in group_blocks
                if str(block.get("block_type") or "").strip()
            ]
            object_types = [
                str(block.get("object_type") or "").strip()
                for block in group_blocks
                if str(block.get("object_type") or "").strip()
            ]

            chunk_text = self._build_slide_chunk_text(
                document=document,
                slide_title=slide_title,
                slide_number=slide_number,
                slide_layout=slide_layout,
                block_lines=group_lines,
                reading_orders=reading_orders,
            )
            if not chunk_text:
                continue

            chunks.append(
                _with_metadata(
                    document,
                    chunk_text,
                    {
                        "content_type": "slide_block_chunk" if len(groups) > 1 else "slide_chunk",
                        "slide_number": slide_number,
                        "slide_title": slide_title,
                        "slide_layout": slide_layout,
                        "section_title": slide_title,
                        "block_types": sorted(set(block_types)),
                        "object_types": sorted(set(object_types)),
                        "has_table": any(block == "table" for block in block_types),
                        "has_chart": any(block == "chart" for block in block_types),
                        "has_image": any(block in {"image_ocr", "image_vision", "image"} for block in block_types),
                        "has_notes": any(block == "speaker_notes" for block in block_types),
                        "reading_order_start": min(reading_orders) if reading_orders else 0,
                        "reading_order_end": max(reading_orders) if reading_orders else 0,
                        "structure_path": _compose_structure_path(
                            f"Slide: {slide_number}" if slide_number > 0 else "Slide",
                            slide_title,
                            (
                                f"Blocks: {min(reading_orders)}-{max(reading_orders)}"
                                if reading_orders
                                else None
                            ),
                        ),
                    },
                    exclude_metadata_keys={"slide_blocks"},
                )
            )

        return chunks

    @staticmethod
    def _pack_blocks(
        block_units: list[tuple[dict, str]],
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[list[tuple[dict, str]]]:
        groups: list[list[tuple[dict, str]]] = []
        current_group: list[tuple[dict, str]] = []
        current_chars = 0

        for block_unit in block_units:
            projected = current_chars + len(block_unit[1]) + (1 if current_group else 0)
            if current_group and projected > chunk_size:
                groups.append(current_group)

                if chunk_overlap > 0:
                    carry: list[tuple[dict, str]] = []
                    carry_chars = 0
                    for candidate in reversed(current_group):
                        candidate_chars = len(candidate[1]) + (1 if carry else 0)
                        if carry_chars + candidate_chars > chunk_overlap:
                            break
                        carry.insert(0, candidate)
                        carry_chars += candidate_chars
                    current_group = carry
                    current_chars = sum(len(item[1]) for item in current_group) + max(0, len(current_group) - 1)
                else:
                    current_group = []
                    current_chars = 0

            current_group.append(block_unit)
            current_chars += len(block_unit[1]) + (1 if len(current_group) > 1 else 0)

        if current_group:
            groups.append(current_group)

        return groups

    @staticmethod
    def _format_block_text(block: dict) -> str:
        block_type = str(block.get("block_type") or "object").strip()
        object_type = str(block.get("object_type") or "unknown").strip()
        reading_order = int(block.get("reading_order", 0) or 0)
        position = str(block.get("position") or "").strip()
        content = _normalized_text(str(block.get("content") or ""))

        if not content:
            return ""

        prefix = f"[{reading_order}] {block_type}/{object_type}"
        if position:
            prefix += f" @ {position}"
        return f"{prefix}: {content}".strip()

    @staticmethod
    def _build_slide_chunk_text(
        *,
        document: Document,
        slide_title: str,
        slide_number: int,
        slide_layout: str,
        block_lines: list[str],
        reading_orders: list[int],
    ) -> str:
        if not block_lines:
            return ""

        file_name = str(document.metadata.get("file_name") or document.metadata.get("document_name") or "")
        lines = [
            f"File: {file_name}" if file_name else "File: unknown",
            f"Slide: {slide_number}",
            f"Title: {slide_title}",
            f"Layout: {slide_layout}" if slide_layout else "",
            (
                f"Reading Order: {min(reading_orders)}-{max(reading_orders)}"
                if reading_orders
                else "Reading Order: n/a"
            ),
            "Slide Blocks:",
        ]
        lines.extend(f"- {line}" for line in block_lines)
        return _normalized_text("\n".join(line for line in lines if line))

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
            page_number = document.metadata.get("page_number") or document.metadata.get("page")
            chunks.append(
                _with_metadata(
                    document,
                    chunk_text,
                    {
                        "section_title": section_title,
                        "structure_path": _compose_structure_path(
                            f"Page: {page_number}" if page_number is not None else None,
                            section_title if section_title != "paragraph" else None,
                            None if page_number is not None or section_title != "paragraph" else "paragraph",
                        ),
                    },
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
        profile_key = self.profile_key(document)
        if profile_key == "structured":
            return self._structured
        if profile_key == "section":
            return self._section
        if profile_key == "slide":
            return self._slide
        if profile_key == "image":
            return self._structured
        if profile_key == "paragraph":
            return self._paragraph
        return self._paragraph

    @staticmethod
    def profile_key(document: Document) -> str:
        extension = _normalized_extension(document)
        if extension in _STRUCTURED_EXTENSIONS:
            return "structured"
        if extension in _SECTION_EXTENSIONS:
            return "section"
        if extension in _SLIDE_EXTENSIONS:
            return "slide"
        if extension in _IMAGE_EXTENSIONS:
            return "image"
        if extension in _PARAGRAPH_EXTENSIONS:
            return "paragraph"
        return "paragraph"
