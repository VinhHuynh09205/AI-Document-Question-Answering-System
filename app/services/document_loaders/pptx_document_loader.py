from pathlib import Path
import re
import time

from langchain_core.documents import Document
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx import Presentation

from app.services.interfaces.document_loader import IDocumentLoader
from app.services.interfaces.image_understanding_service import IImageUnderstandingService


class PptxDocumentLoader(IDocumentLoader):
    _OCR_MARKER_RE = re.compile(
        r"(local_ocr|local_vision|image\s*analysis|slide\s*image|provider[:=])",
        re.IGNORECASE,
    )
    _LATIN_WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F]{2,}")
    _CJK_RE = re.compile(r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]")
    _DECORATIVE_LINE_RE = re.compile(
        r"^(?:\d{1,3}|page\s*\d{1,3}|slide\s*\d{1,3}|\d{1,3}/\d{1,3})$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        image_understanding_service: IImageUnderstandingService | None = None,
        *,
        max_images_per_slide: int = 2,
        max_images_per_document: int = 24,
        text_char_threshold_for_image_analysis: int = 950,
        max_image_analysis_seconds: float = 25.0,
    ) -> None:
        self._image_understanding_service = image_understanding_service
        self._max_images_per_slide = max(1, max_images_per_slide)
        self._max_images_per_document = max(1, max_images_per_document)
        self._text_char_threshold_for_image_analysis = max(250, text_char_threshold_for_image_analysis)
        self._max_image_analysis_seconds = max(1.0, float(max_image_analysis_seconds))

    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".pptx"

    def load(self, file_path: Path) -> list[Document]:
        prs = Presentation(str(file_path))
        documents: list[Document] = []
        repeated_lines = self._detect_repeated_slide_lines(prs)
        image_analysis_started_at = time.perf_counter()
        total_images_analyzed = 0

        for slide_index, slide in enumerate(prs.slides, start=1):
            parts: list[str] = []
            image_notes: list[str] = []
            providers_used: set[str] = set()
            image_counter = 0
            slide_lines: list[str] = []

            slide_title = ""
            title_shape = getattr(slide.shapes, "title", None)
            if title_shape is not None:
                slide_title = str(getattr(title_shape, "text", "") or "").strip()
            if slide_title:
                parts.append(f"# {slide_title}")

            for shape in slide.shapes:
                if title_shape is not None and shape == title_shape:
                    continue

                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        text = self._normalize_slide_line(paragraph.text)
                        if not text:
                            continue
                        if text.casefold() in repeated_lines:
                            continue
                        if self._looks_decorative_slide_line(text):
                            continue
                        if slide_title and text.casefold() == slide_title.casefold():
                            continue
                        slide_lines.append(text)

                if shape.has_table:
                    for row in shape.table.rows:
                        cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if cells:
                            slide_lines.append(" | ".join(cells))

            deduplicated_lines: list[str] = []
            seen_lines: set[str] = set()
            for line in slide_lines:
                line_key = line.casefold()
                if line_key in seen_lines:
                    continue
                seen_lines.add(line_key)
                deduplicated_lines.append(line)

            parts.extend(deduplicated_lines)

            slide_text_snapshot = "\n".join(parts)
            slide_prefers_cjk = self._contains_substantial_cjk(slide_text_snapshot)

            if self._should_analyze_slide_images(
                text_snapshot=slide_text_snapshot,
                total_images_analyzed=total_images_analyzed,
                started_at=image_analysis_started_at,
            ):
                for shape in slide.shapes:
                    if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                        continue

                    image_counter += 1
                    if image_counter > self._max_images_per_slide:
                        break
                    if total_images_analyzed >= self._max_images_per_document:
                        break
                    if (time.perf_counter() - image_analysis_started_at) >= self._max_image_analysis_seconds:
                        break

                    image_bytes = getattr(getattr(shape, "image", None), "blob", b"")
                    if not image_bytes:
                        continue

                    result = self._image_understanding_service.analyze_image(
                        image_bytes,
                        source=str(file_path),
                        hint=f"pptx slide {slide_index} image {image_counter}",
                    )
                    total_images_analyzed += 1
                    providers_used.add(str(result.provider or "").strip().lower())

                    note_text = self._normalize_image_note_text(str(result.text or ""))
                    if not note_text:
                        continue
                    if not self._is_useful_image_note(
                        note_text,
                        slide_prefers_cjk=slide_prefers_cjk,
                    ):
                        continue
                    if self._is_duplicate_image_note(
                        note_text,
                        slide_text_snapshot,
                        image_notes,
                    ):
                        continue
                    image_notes.append(f"Image {image_counter}: {note_text}")

            if getattr(slide, "has_notes_slide", False):
                try:
                    notes_text = str(slide.notes_slide.notes_text_frame.text or "").strip()
                except Exception:
                    notes_text = ""
                if notes_text:
                    parts.append("[Slide notes]")
                    parts.append(notes_text)

            if image_notes:
                parts.append("[Image insights]")
                parts.extend(image_notes)

            content = "\n".join(parts)
            if content.strip():
                documents.append(
                    Document(
                        page_content=content,
                        metadata={
                            "source": str(file_path),
                            "slide": slide_index,
                            "slide_title": slide_title,
                            "extension": ".pptx",
                            "content_type": "slide",
                            "image_analysis_applied": bool(image_notes),
                            "ocr_applied": "local_ocr" in providers_used,
                        },
                    )
                )

        return documents

    @classmethod
    def _normalize_slide_line(cls, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip(" -•\t")

    @classmethod
    def _looks_decorative_slide_line(cls, text: str) -> bool:
        compact = str(text or "").strip()
        if not compact:
            return True
        if cls._DECORATIVE_LINE_RE.match(compact):
            return True
        if len(compact) <= 2:
            return True
        return False

    def _should_analyze_slide_images(
        self,
        *,
        text_snapshot: str,
        total_images_analyzed: int,
        started_at: float,
    ) -> bool:
        if self._image_understanding_service is None:
            return False

        if total_images_analyzed >= self._max_images_per_document:
            return False

        elapsed_seconds = time.perf_counter() - started_at
        if elapsed_seconds >= self._max_image_analysis_seconds:
            return False

        compact_text = str(text_snapshot or "").strip()
        if not compact_text:
            return True

        if len(compact_text) >= self._text_char_threshold_for_image_analysis:
            return False

        if len(self._LATIN_WORD_RE.findall(compact_text)) >= 120:
            return False

        return True

    @classmethod
    def _detect_repeated_slide_lines(cls, presentation: Presentation) -> set[str]:
        line_counts: dict[str, int] = {}
        total_slides = max(1, len(presentation.slides))
        threshold = max(3, int(total_slides * 0.5))

        for slide in presentation.slides:
            seen_in_slide: set[str] = set()
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                for paragraph in shape.text_frame.paragraphs:
                    line = cls._normalize_slide_line(paragraph.text)
                    if not line:
                        continue
                    if cls._looks_decorative_slide_line(line):
                        continue

                    key = line.casefold()
                    if key in seen_in_slide:
                        continue
                    seen_in_slide.add(key)
                    line_counts[key] = line_counts.get(key, 0) + 1

        return {
            line for line, count in line_counts.items()
            if count >= threshold and len(line) <= 90
        }

    @classmethod
    def _normalize_image_note_text(cls, text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        cleaned_lines: list[str] = []
        seen: set[str] = set()

        for raw_line in normalized.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" -•\t")
            if not line:
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
        slide_prefers_cjk: bool,
    ) -> bool:
        compact = " ".join(str(note_text or "").split()).strip()
        if len(compact) < 8:
            return False

        if cls._OCR_MARKER_RE.search(compact):
            return False

        has_cjk = bool(cls._CJK_RE.search(compact))
        if slide_prefers_cjk and not has_cjk:
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
        slide_text_snapshot: str,
        existing_notes: list[str],
    ) -> bool:
        compact_note = re.sub(r"\s+", " ", str(note_text or "")).strip().lower()
        if not compact_note:
            return True

        compact_slide = re.sub(r"\s+", " ", str(slide_text_snapshot or "")).strip().lower()
        if compact_note in compact_slide:
            return True

        for existing in existing_notes:
            _, _, existing_note = existing.partition(":")
            normalized_existing = re.sub(r"\s+", " ", existing_note).strip().lower()
            if compact_note == normalized_existing:
                return True

        return False
