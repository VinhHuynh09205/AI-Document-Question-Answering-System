from pathlib import Path
import re
import time
from zipfile import ZipFile

from docx import Document as DocxDocument
from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader
from app.services.interfaces.image_understanding_service import IImageUnderstandingService


class DocxDocumentLoader(IDocumentLoader):
    _OCR_MARKER_RE = re.compile(
        r"(local_ocr|local_vision|image\s*analysis|slide\s*image|provider[:=])",
        re.IGNORECASE,
    )
    _LATIN_WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F]{2,}")
    _CJK_RE = re.compile(r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]")
    _HEADING_LEVEL_RE = re.compile(r"heading\s*(\d+)", re.IGNORECASE)

    def __init__(
        self,
        image_understanding_service: IImageUnderstandingService | None = None,
        *,
        max_images_per_document: int = 4,
        text_char_threshold_for_image_analysis: int = 2200,
        max_image_analysis_seconds: float = 20.0,
    ) -> None:
        self._image_understanding_service = image_understanding_service
        self._max_images_per_document = max(1, max_images_per_document)
        self._text_char_threshold_for_image_analysis = max(300, text_char_threshold_for_image_analysis)
        self._max_image_analysis_seconds = max(1.0, float(max_image_analysis_seconds))

    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".docx"

    def load(self, file_path: Path) -> list[Document]:
        doc = DocxDocument(str(file_path))

        paragraph_lines = self._extract_paragraph_lines(doc)
        table_lines = self._extract_table_lines(doc)

        body_text_snapshot = "\n".join(paragraph_lines + table_lines)
        image_notes, providers_used = self._extract_docx_image_notes(file_path, body_text_snapshot)
        content_parts = paragraph_lines + table_lines
        if image_notes:
            content_parts.append("[Image insights]")
            content_parts.extend(image_notes)

        content = "\n".join(content_parts)
        return [
            Document(
                page_content=content,
                metadata={
                    "source": str(file_path),
                    "extension": ".docx",
                    "content_type": "docx_document",
                    "image_analysis_applied": bool(image_notes),
                    "ocr_applied": "local_ocr" in providers_used,
                },
            )
        ]

    @classmethod
    def _extract_paragraph_lines(cls, doc: DocxDocument) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()

        for paragraph in doc.paragraphs:
            raw_text = str(paragraph.text or "")
            text = re.sub(r"\s+", " ", raw_text).strip()
            if not text:
                continue

            style_name = str(getattr(getattr(paragraph, "style", None), "name", "") or "").strip()
            normalized_style = style_name.lower()

            heading_match = cls._HEADING_LEVEL_RE.search(normalized_style)
            if heading_match:
                level = max(1, min(6, int(heading_match.group(1))))
                line = f"{'#' * level} {text}"
            elif "list" in normalized_style or text.startswith(("- ", "* ", "• ")):
                clean_text = text.lstrip("-*• ").strip()
                line = f"- {clean_text}" if clean_text else ""
            else:
                line = text

            if not line:
                continue

            dedupe_key = line.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            lines.append(line)

        return lines

    @staticmethod
    def _extract_table_lines(doc: DocxDocument) -> list[str]:
        lines: list[str] = []
        for table in doc.tables:
            for row in table.rows:
                cells = [re.sub(r"\s+", " ", cell.text).strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    lines.append(" | ".join(cells))
        return lines

    def _extract_docx_image_notes(
        self,
        file_path: Path,
        text_snapshot: str,
    ) -> tuple[list[str], set[str]]:
        if self._image_understanding_service is None:
            return [], set()

        compact_text = str(text_snapshot or "").strip()
        if len(compact_text) >= self._text_char_threshold_for_image_analysis:
            return [], set()

        started_at = time.perf_counter()
        notes: list[str] = []
        providers_used: set[str] = set()
        doc_prefers_cjk = self._contains_substantial_cjk(text_snapshot)

        try:
            with ZipFile(file_path, "r") as archive:
                media_entries = [
                    name for name in archive.namelist()
                    if name.startswith("word/media/") and not name.endswith("/")
                ]
                for image_index, entry_name in enumerate(media_entries, start=1):
                    if image_index > self._max_images_per_document:
                        break
                    if (time.perf_counter() - started_at) >= self._max_image_analysis_seconds:
                        break

                    image_bytes = archive.read(entry_name)
                    if not image_bytes:
                        continue

                    result = self._image_understanding_service.analyze_image(
                        image_bytes,
                        source=str(file_path),
                        hint=f"docx image {image_index}",
                    )
                    providers_used.add(str(result.provider or "").strip().lower())
                    note_text = self._normalize_image_note_text(str(result.text or ""))
                    if not note_text:
                        continue

                    if not self._is_useful_image_note(
                        note_text,
                        document_prefers_cjk=doc_prefers_cjk,
                    ):
                        continue

                    if self._is_duplicate_image_note(
                        note_text,
                        text_snapshot,
                        notes,
                    ):
                        continue

                    notes.append(f"Image {image_index}: {note_text}")
        except OSError:
            return [], set()

        return notes, providers_used

    @classmethod
    def _normalize_image_note_text(cls, text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        cleaned_lines: list[str] = []
        seen: set[str] = set()

        for raw_line in normalized.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" -•\t")
            if not line:
                continue
            if cls._OCR_MARKER_RE.search(line):
                continue

            lowered = line.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned_lines.append(line)
            if len(cleaned_lines) >= 3:
                break

        return "\n".join(cleaned_lines).strip()

    @classmethod
    def _contains_substantial_cjk(cls, text: str) -> bool:
        return len(cls._CJK_RE.findall(str(text or ""))) >= 6

    @classmethod
    def _is_useful_image_note(
        cls,
        note_text: str,
        *,
        document_prefers_cjk: bool,
    ) -> bool:
        compact = " ".join(str(note_text or "").split()).strip()
        if len(compact) < 8:
            return False

        if cls._OCR_MARKER_RE.search(compact):
            return False

        has_cjk = bool(cls._CJK_RE.search(compact))
        if document_prefers_cjk and not has_cjk:
            return False

        stripped_symbols = re.sub(
            r"[A-Za-z\u00C0-\u024F0-9\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\s]",
            "",
            compact,
        )
        if len(stripped_symbols) > len(compact) * 0.35:
            return False

        if not has_cjk and len(cls._LATIN_WORD_RE.findall(compact)) < 2:
            return False

        return True

    @staticmethod
    def _is_duplicate_image_note(
        note_text: str,
        text_snapshot: str,
        existing_notes: list[str],
    ) -> bool:
        compact_note = re.sub(r"\s+", " ", str(note_text or "")).strip().lower()
        if not compact_note:
            return True

        compact_doc = re.sub(r"\s+", " ", str(text_snapshot or "")).strip().lower()
        if compact_note in compact_doc:
            return True

        for existing in existing_notes:
            _, _, existing_note = existing.partition(":")
            normalized_existing = re.sub(r"\s+", " ", existing_note).strip().lower()
            if compact_note == normalized_existing:
                return True

        return False
