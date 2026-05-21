from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


_SLIDE_NUMBER_HINT_RE = re.compile(r"\bslide\s*(\d{1,3})\b", re.IGNORECASE)
_PAGE_NUMBER_HINT_RE = re.compile(
    r"\b(?:page|trang)\s*(\d{1,4})\b",
    re.IGNORECASE,
)
_SHEET_HINT_RE = re.compile(r"\b(sheet\s*[a-z0-9_]+)\b", re.IGNORECASE)
_GENERIC_SHEET_HINT_TOKENS = {
    "bao",
    "co",
    "count",
    "danh",
    "gi",
    "list",
    "may",
    "nao",
    "nhieu",
    "sach",
    "ten",
    "va",
}
_RANGE_HINT_RE = re.compile(r"\b([A-Z]{1,3}\d{1,6}:[A-Z]{1,3}\d{1,6})\b")
_FILENAME_HINT_RE = re.compile(
    r"\b([A-Za-z0-9][A-Za-z0-9._ -]{0,120}\.(?:pdf|docx|pptx|xlsx|xls|txt|md|png|jpg|jpeg))\b",
    re.IGNORECASE,
)
_TABLE_CALC_HINT_RE = re.compile(
    r"\b(sum|total|tong|average|avg|trung\s*binh|min|max|lowest|highest|"
    r"count|group\s*by|nhom\s*theo|compare|so\s*sanh|top|bottom|lọc|loc)\b",
    re.IGNORECASE,
)
_TABLE_LOOKUP_HINT_RE = re.compile(
    r"\b(lookup|tra\s*cứu|tra\s*cuu|liet\s*ke|liệt\s*kê|co\s*nhung|nhung|"
    r"row|dong|dòng|sheet|excel|xlsx|xls|table|bang|bảng|"
    r"thi\s*sinh|hoc\s*vien|student|no\.?\s*\d{1,4})\b",
    re.IGNORECASE,
)
_IMAGE_OCR_HINT_RE = re.compile(
    r"\b(ocr|scan|trich\s*xuat\s*chu|trích\s*xuất\s*chữ|text\s*trong\s*anh|text\s*in\s*image)\b",
    re.IGNORECASE,
)
_DIAGRAM_OR_CHART_HINT_RE = re.compile(
    r"\b(diagram|chart|flowchart|mindmap|mermaid|biểu\s*đồ|bieu\s*do|sơ\s*đồ|so\s*do)\b",
    re.IGNORECASE,
)
_FILE_REFERENCE_HINT_RE = re.compile(r"\b(file|tài\s*liệu|tai\s*lieu|document)\b", re.IGNORECASE)
_COMPARISON_HINT_RE = re.compile(r"\b(compare|comparison|so\s*sanh|doi\s*chieu|đối\s*chiếu)\b", re.IGNORECASE)
_OUT_OF_SCOPE_HINT_RE = re.compile(
    r"\b(ngoài\s*tài\s*liệu|ngoai\s*tai\s*lieu|outside\s*the\s*document|không\s*có\s*trong\s*tài\s*liệu|not\s*in\s*the\s*document)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class QueryRoute:
    intent: str
    metadata_filter: dict[str, str | list[str]] | None
    explicit_filename: str = ""
    explicit_page_number: int | None = None
    explicit_slide_number: int | None = None
    explicit_sheet_name: str = ""
    explicit_range_address: str = ""


class QueryRouter:
    def route(
        self,
        question: str,
        metadata_filter: dict[str, str | list[str]] | None = None,
    ) -> QueryRoute:
        explicit_filename = self.extract_filename_hint(question)
        explicit_page_number = self.extract_page_number_hint(question)
        explicit_slide_number = self.extract_slide_number_hint(question)
        explicit_sheet_name = self.extract_sheet_hint(question)
        explicit_range_address = self.extract_range_hint(question)
        merged_filter = self.build_metadata_filter(question, metadata_filter)

        intent = self.classify_intent(
            question,
            metadata_filter=merged_filter,
            explicit_filename=explicit_filename,
            explicit_page_number=explicit_page_number,
            explicit_slide_number=explicit_slide_number,
            explicit_sheet_name=explicit_sheet_name,
            explicit_range_address=explicit_range_address,
        )
        return QueryRoute(
            intent=intent,
            metadata_filter=merged_filter,
            explicit_filename=explicit_filename,
            explicit_page_number=explicit_page_number,
            explicit_slide_number=explicit_slide_number,
            explicit_sheet_name=explicit_sheet_name,
            explicit_range_address=explicit_range_address,
        )

    def classify_intent(
        self,
        question: str,
        *,
        metadata_filter: dict[str, str | list[str]] | None,
        explicit_filename: str = "",
        explicit_page_number: int | None = None,
        explicit_slide_number: int | None = None,
        explicit_sheet_name: str = "",
        explicit_range_address: str = "",
    ) -> str:
        folded_question = self.fold_text(question)
        sources = self._count_filter_values(metadata_filter, "source")

        if _OUT_OF_SCOPE_HINT_RE.search(folded_question):
            return "negative_or_out_of_scope_question"
        if _COMPARISON_HINT_RE.search(folded_question) and (sources > 1 or self._count_explicit_filenames(question) > 1):
            return "multi_file_comparison"
        if explicit_page_number is not None:
            return "specific_page_question"
        if explicit_slide_number is not None:
            return "specific_slide_question"
        if explicit_sheet_name or explicit_range_address:
            if _TABLE_CALC_HINT_RE.search(folded_question):
                return "table_calculation_question"
            if _TABLE_LOOKUP_HINT_RE.search(folded_question):
                return "specific_sheet_question"
            return "specific_sheet_question"
        if _IMAGE_OCR_HINT_RE.search(folded_question):
            return "image_ocr_question"
        if _DIAGRAM_OR_CHART_HINT_RE.search(folded_question):
            return "diagram_or_chart_question"
        if _TABLE_CALC_HINT_RE.search(folded_question) and _TABLE_LOOKUP_HINT_RE.search(folded_question):
            return "table_calculation_question"
        if _TABLE_LOOKUP_HINT_RE.search(folded_question):
            return "table_lookup_question"
        if explicit_filename or (sources == 1 and _FILE_REFERENCE_HINT_RE.search(folded_question)):
            return "specific_file_question"
        return "normal_text_question"

    def build_metadata_filter(
        self,
        question: str,
        metadata_filter: dict[str, str | list[str]] | None,
    ) -> dict[str, str | list[str]] | None:
        merged_filter = dict(metadata_filter or {})

        slide_number_hint = self.extract_slide_number_hint(question)
        if slide_number_hint is not None:
            merged_filter["slide_number"] = str(slide_number_hint)

        page_number_hint = self.extract_page_number_hint(question)
        if page_number_hint is not None:
            merged_filter["page_number"] = str(page_number_hint)
            merged_filter["page"] = str(page_number_hint)

        sheet_hint = self.extract_sheet_hint(question)
        if sheet_hint:
            merged_filter["sheet_name"] = sheet_hint

        range_hint = self.extract_range_hint(question)
        if range_hint:
            merged_filter["range_address"] = range_hint

        filename_hint = self.extract_filename_hint(question)
        if filename_hint and "source" not in merged_filter:
            merged_filter["source"] = filename_hint

        hinted_extensions = self.infer_extension_hints(question)
        if not hinted_extensions:
            return merged_filter or None

        current_extension = merged_filter.get("extension")
        if current_extension is None:
            merged_filter["extension"] = sorted(hinted_extensions)
            return merged_filter

        current_values = self.normalize_filter_values(current_extension)
        intersection = [value for value in current_values if value in hinted_extensions]
        if not intersection:
            return metadata_filter

        merged_filter["extension"] = intersection if len(intersection) > 1 else intersection[0]
        return merged_filter

    @staticmethod
    def extract_slide_number_hint(question: str) -> int | None:
        raw_question = str(question or "")
        folded_question = QueryRouter.fold_text(raw_question)
        if re.search(r"\bslide\s*(?:dau|dau\s*tien|first)\b", folded_question):
            return 1

        match = _SLIDE_NUMBER_HINT_RE.search(raw_question)
        if match is None:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def extract_page_number_hint(question: str) -> int | None:
        raw_question = str(question or "")
        folded_question = QueryRouter.fold_text(raw_question)
        if re.search(r"\b(?:page|trang)\s*(?:dau|dau\s*tien|first)\b", folded_question):
            return 1

        match = _PAGE_NUMBER_HINT_RE.search(raw_question)
        if match is None:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def extract_sheet_hint(question: str) -> str:
        match = _SHEET_HINT_RE.search(str(question or ""))
        if match is None:
            return ""
        raw_hint = match.group(1).strip()
        if " " in raw_hint:
            candidate = raw_hint.split(None, 1)[1].strip()
        else:
            candidate = raw_hint[5:].strip()

        folded_candidate = QueryRouter.fold_text(candidate)
        if not folded_candidate or folded_candidate in _GENERIC_SHEET_HINT_TOKENS:
            return ""
        if folded_candidate.isdigit():
            return f"Sheet{folded_candidate}"
        return candidate

    @staticmethod
    def extract_range_hint(question: str) -> str:
        match = _RANGE_HINT_RE.search(str(question or ""))
        if match is None:
            return ""
        return match.group(1).upper()

    @staticmethod
    def extract_filename_hint(question: str) -> str:
        match = _FILENAME_HINT_RE.search(str(question or ""))
        if match is None:
            return ""
        candidate = match.group(1).strip()
        tokens = candidate.split()
        if not tokens:
            return ""

        stopwords = {
            "file", "trong", "page", "trang", "slide", "sheet", "ở", "o", "in", "of", "with", "va",
        }

        selected: list[str] = []
        for token in reversed(tokens):
            clean_token = token.strip()
            folded_token = QueryRouter.fold_text(clean_token)
            if selected and (not folded_token or folded_token in stopwords or folded_token.isdigit()):
                break
            if not selected and "." not in clean_token:
                continue
            selected.insert(0, clean_token)

        if selected:
            return " ".join(selected)
        return candidate

    @classmethod
    def infer_extension_hints(cls, question: str) -> set[str]:
        folded_question = cls.fold_text(question)
        hints: set[str] = set()

        if re.search(r"\b(slide|ppt|presentation)\b", folded_question):
            hints.update({"ppt", "pptx"})

        if re.search(r"\b(sheet\s*[a-z0-9_]+|sheet|spreadsheet|excel|xls|xlsx|thi\s*sinh|hoc\s*vien|student)\b", folded_question):
            hints.update({"xls", "xlsx"})

        if re.search(r"\b(section|chapter|heading|muc|chuong|docx|markdown|md)\b", folded_question):
            hints.update({"pdf", "docx", "md", "txt"})

        if re.search(r"\b(image|figure|diagram|screenshot|chart|anh|hinh|scan|ocr)\b", folded_question):
            hints.update({"png", "jpg", "jpeg", "pdf", "pptx", "docx"})

        filename_hint = cls.extract_filename_hint(question)
        if filename_hint and "." in filename_hint:
            hints.add(filename_hint.rsplit(".", 1)[-1].lower())

        return hints

    @staticmethod
    def normalize_filter_values(value: str | list[str]) -> list[str]:
        values = value if isinstance(value, list) else [value]
        normalized: list[str] = []
        for item in values:
            normalized_value = str(item).lower().lstrip(".").strip()
            if not normalized_value:
                continue
            if normalized_value not in normalized:
                normalized.append(normalized_value)
        return normalized

    @staticmethod
    def fold_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        lowercase = without_marks.replace("Đ", "D").replace("đ", "d").lower()
        stripped = re.sub(r"[^a-z0-9.\s\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]+", " ", lowercase)
        return re.sub(r"\s+", " ", stripped).strip()

    @staticmethod
    def _count_filter_values(
        metadata_filter: dict[str, str | list[str]] | None,
        key: str,
    ) -> int:
        if not metadata_filter:
            return 0
        value = metadata_filter.get(key)
        if isinstance(value, list):
            return len([item for item in value if str(item or "").strip()])
        return 1 if str(value or "").strip() else 0

    @staticmethod
    def _count_explicit_filenames(question: str) -> int:
        return len(_FILENAME_HINT_RE.findall(str(question or "")))
