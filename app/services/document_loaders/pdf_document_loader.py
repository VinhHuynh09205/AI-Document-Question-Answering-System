from pathlib import Path
import hashlib
import re
import time

from langchain_core.documents import Document
from pypdf import PdfReader

from app.services.interfaces.document_loader import IDocumentLoader
from app.services.interfaces.image_understanding_service import IImageUnderstandingService


class PdfDocumentLoader(IDocumentLoader):
    _OCR_MARKER_RE = re.compile(
        r"(local_ocr|local_vision|image\s*analysis|slide\s*image|provider[:=])",
        re.IGNORECASE,
    )
    _LATIN_WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F]{2,}")
    _CJK_RE = re.compile(r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]")
    _NUMERIC_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?")

    def __init__(
        self,
        image_understanding_service: IImageUnderstandingService | None = None,
        *,
        max_images_per_page: int = 2,
        max_pages_with_image_analysis: int = 12,
        text_char_threshold_for_image_analysis: int = 900,
        max_image_analysis_seconds: float = 20.0,
    ) -> None:
        self._image_understanding_service = image_understanding_service
        self._max_images_per_page = max(1, max_images_per_page)
        self._max_pages_with_image_analysis = max(1, max_pages_with_image_analysis)
        self._text_char_threshold_for_image_analysis = max(200, text_char_threshold_for_image_analysis)
        self._max_image_analysis_seconds = max(1.0, float(max_image_analysis_seconds))

    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".pdf"

    def load(self, file_path: Path) -> list[Document]:
        reader = PdfReader(str(file_path))
        documents: list[Document] = []
        image_analysis_started_at = time.perf_counter()
        analyzed_pages = 0
        seen_image_hashes: set[str] = set()

        for index, page in enumerate(reader.pages, start=1):
            text = self._extract_page_text(page)
            image_notes: list[str] = []
            providers_used: set[str] = set()
            page_images = list(getattr(page, "images", []) or [])

            should_analyze_images = self._should_analyze_page_images(
                text=text,
                analyzed_pages=analyzed_pages,
                started_at=image_analysis_started_at,
                page_image_count=len(page_images),
            )
            if should_analyze_images:
                image_notes, providers_used = self._analyze_page_images(
                    page_images=page_images,
                    file_path=file_path,
                    page_number=index,
                    page_text_snapshot=text,
                    seen_image_hashes=seen_image_hashes,
                )
                if image_notes:
                    analyzed_pages += 1

            if image_notes:
                text = self._merge_text_and_image_notes(text=text, image_notes=image_notes)

            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": str(file_path),
                        "page": index,
                        "extension": ".pdf",
                        "content_type": "pdf_page",
                        "image_analysis_applied": bool(image_notes),
                        "ocr_applied": "local_ocr" in providers_used,
                    },
                )
            )

        return documents

    def _should_analyze_page_images(
        self,
        *,
        text: str,
        analyzed_pages: int,
        started_at: float,
        page_image_count: int,
    ) -> bool:
        if self._image_understanding_service is None:
            return False

        if page_image_count <= 0:
            return False

        if analyzed_pages >= self._max_pages_with_image_analysis:
            return False

        elapsed_seconds = time.perf_counter() - started_at
        if elapsed_seconds >= self._max_image_analysis_seconds:
            return False

        compact_text = str(text or "").strip()
        if not compact_text:
            return True

        if len(compact_text) < 120:
            return True

        if len(compact_text) >= self._text_char_threshold_for_image_analysis:
            if page_image_count < 2:
                return False
            if len(compact_text) >= int(self._text_char_threshold_for_image_analysis * 1.4):
                return False

        if page_image_count >= 2 and len(compact_text) < int(self._text_char_threshold_for_image_analysis * 1.25):
            return True

        if len(compact_text) >= self._text_char_threshold_for_image_analysis:
            return False

        alpha_words = len(self._LATIN_WORD_RE.findall(compact_text)) + len(self._CJK_RE.findall(compact_text))
        readability_score = self._score_extracted_text(compact_text)
        if alpha_words >= 40 and readability_score >= 10.0:
            return False

        return True

    def _analyze_page_images(
        self,
        *,
        page_images,
        file_path: Path,
        page_number: int,
        page_text_snapshot: str,
        seen_image_hashes: set[str],
    ) -> tuple[list[str], set[str]]:
        if self._image_understanding_service is None:
            return [], set()

        if not page_images:
            return [], set()

        notes: list[str] = []
        providers_used: set[str] = set()
        page_prefers_cjk = self._contains_substantial_cjk(page_text_snapshot)

        for image_index, image in enumerate(page_images, start=1):
            if image_index > self._max_images_per_page:
                break

            image_bytes = getattr(image, "data", b"")
            if not image_bytes:
                continue

            image_hash = self._fingerprint_image_bytes(image_bytes)
            if image_hash in seen_image_hashes:
                continue
            seen_image_hashes.add(image_hash)

            result = self._image_understanding_service.analyze_image(
                image_bytes,
                source=str(file_path),
                hint=f"pdf page {page_number} image {image_index}",
            )
            providers_used.add(str(result.provider or "").strip().lower())
            note_text = self._normalize_image_note_text(str(result.text or ""))
            if not note_text:
                continue

            if not self._is_useful_image_note(
                note_text,
                page_prefers_cjk=page_prefers_cjk,
            ):
                continue

            if self._is_duplicate_image_note(
                note_text,
                page_text_snapshot,
                notes,
            ):
                continue

            notes.append(f"Image {image_index}: {note_text}")

        return notes, providers_used

    @staticmethod
    def _fingerprint_image_bytes(image_bytes: bytes) -> str:
        return hashlib.sha1(image_bytes).hexdigest()[:24]

    @staticmethod
    def _merge_text_and_image_notes(*, text: str, image_notes: list[str]) -> str:
        merged_notes = "\n\n".join(image_notes).strip()
        if not merged_notes:
            return str(text or "").strip()

        base_text = str(text or "").strip()
        if not base_text:
            return f"[Image insights]\n{merged_notes}".strip()

        return f"{base_text}\n\n[Image insights]\n{merged_notes}".strip()

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
            if cls._OCR_MARKER_RE.search(line):
                continue

            seen.add(lowered)
            cleaned_lines.append(line)
            if len(cleaned_lines) >= 5:
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
        page_prefers_cjk: bool,
    ) -> bool:
        compact = " ".join(str(note_text or "").split()).strip()
        if len(compact) < 8:
            return False

        if cls._OCR_MARKER_RE.search(compact):
            return False

        has_cjk = bool(cls._CJK_RE.search(compact))
        if page_prefers_cjk and not has_cjk:
            return False

        stripped_symbols = re.sub(
            r"[A-Za-z\u00C0-\u024F0-9\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\s]",
            "",
            compact,
        )
        if len(stripped_symbols) > len(compact) * 0.35:
            return False

        if not has_cjk:
            latin_word_count = len(cls._LATIN_WORD_RE.findall(compact))
            if latin_word_count < 2:
                numeric_count = len(cls._NUMERIC_TOKEN_RE.findall(compact))
                if not (
                    (latin_word_count >= 1 and numeric_count >= 3)
                    or numeric_count >= 5
                    or "%" in compact
                ):
                    return False

        return True

    @staticmethod
    def _is_duplicate_image_note(
        note_text: str,
        page_text_snapshot: str,
        existing_notes: list[str],
    ) -> bool:
        compact_note = re.sub(r"\s+", " ", str(note_text or "")).strip().lower()
        if not compact_note:
            return True

        compact_page = re.sub(r"\s+", " ", str(page_text_snapshot or "")).strip().lower()
        if compact_note in compact_page:
            return True

        for existing in existing_notes:
            _, _, existing_note = existing.partition(":")
            normalized_existing = re.sub(r"\s+", " ", existing_note).strip().lower()
            if compact_note == normalized_existing:
                return True

        return False

    @classmethod
    def _extract_page_text(cls, page) -> str:
        candidates: list[str] = []

        for extraction_mode in ("layout", "plain"):
            try:
                text = page.extract_text(extraction_mode=extraction_mode) or ""
            except TypeError:
                if extraction_mode != "plain":
                    continue
                text = page.extract_text() or ""

            normalized = cls._normalize_extracted_text(text)
            if normalized:
                candidates.append(normalized)

        if not candidates:
            return ""

        return max(candidates, key=cls._score_extracted_text)

    @staticmethod
    def _normalize_extracted_text(text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\u00A0", " ")
        normalized = re.sub(r"[ \t]+$", "", normalized, flags=re.MULTILINE)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @staticmethod
    def _score_extracted_text(text: str) -> float:
        if not text:
            return float("-inf")

        words = re.findall(r"\S+", text)
        alpha_words = [word for word in words if re.search(r"[A-Za-zÀ-ỹ]", word)]
        whitespace_count = len(re.findall(r"\s", text))
        newline_count = text.count("\n")
        punctuation_count = len(re.findall(r"[:;,.\-•]", text))
        very_long_tokens = sum(1 for word in alpha_words if len(word) >= 20)
        ultra_long_tokens = sum(1 for word in alpha_words if len(word) >= 28)

        return (
            len(alpha_words) * 0.2
            + whitespace_count * 0.12
            + newline_count * 1.8
            + punctuation_count * 0.35
            - very_long_tokens * 4.0
            - ultra_long_tokens * 8.0
        )
