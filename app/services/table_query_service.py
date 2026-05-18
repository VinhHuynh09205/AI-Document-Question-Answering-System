from __future__ import annotations

import json
import re
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from langchain_core.documents import Document


_COMPARE_HINT_RE = re.compile(r"\b(so\s*sanh|compare)\b", re.IGNORECASE)
_GROUP_BY_HINT_RE = re.compile(r"\b(group\s*by|theo|per|moi\s*|mỗi|tung|từng)\b", re.IGNORECASE)
_FILTER_ROW_HINT_RE = re.compile(
    r"\b(liet\s*ke|liệt\s*kê|show|list|nhung\s*dong|những\s*dòng|dong\s*nao|dòng\s*nào|rows?\s+where|filtered)\b",
    re.IGNORECASE,
)
_TOP_BOTTOM_RE = re.compile(
    r"\b(?:(top|bottom)\s*(\d{1,2})?|cao\s*nhat|cao\s*nhất|lon\s*nhat|lớn\s*nhất|nhieu\s*nhat|nhiều\s*nhất|thap\s*nhat|thấp\s*nhất|nho\s*nhat|nhỏ\s*nhất|it\s*nhat|ít\s*nhất)\b",
    re.IGNORECASE,
)
_TOPK_RETRIEVAL_TERM_RE = re.compile(r"\btop\s*-?\s*k\s+retrieval\b|\btopk\s+retrieval\b", re.IGNORECASE)
_COUNT_HINT_RE = re.compile(r"\b(count|bao\s*nhieu|bao\s*nhiêu|so\s*luong|số\s*lượng)\b", re.IGNORECASE)


class TableQueryService:
    def __init__(
        self,
        *,
        try_build_sheet_count_answer: Callable[[str, list[Document]], str],
        try_build_date_lookup_answer: Callable[[str, list[Document]], str],
        try_build_text_count_answer: Callable[[str, list[Document], dict[str, str | list[str]] | None], str],
        try_build_text_list_answer: Callable[[str, list[Document], dict[str, str | list[str]] | None], str],
        try_build_aggregate_answer: Callable[[str, list[Document], dict[str, str | list[str]] | None], str],
        try_build_row_answer: Callable[[str, list[Document]], str],
        expand_spreadsheet_aggregate_docs: Callable[[list[Document], dict[str, str | list[str]] | None], list[Document]],
        load_scoped_context_docs: Callable[[dict[str, str | list[str]] | None], list[Document]],
        resolve_spreadsheet_sheet_hint: Callable[[str, list[Document]], str],
        extract_spreadsheet_structured_rows: Callable[[list[Document], str], list[dict[str, object]]],
        resolve_spreadsheet_aggregate_operation: Callable[[str], str],
        apply_spreadsheet_aggregate_filters: Callable[[list[dict[str, object]], str], list[dict[str, object]]],
        match_spreadsheet_column_by_hint: Callable[[list[dict[str, object]], str], str],
        select_spreadsheet_numeric_column: Callable[[str, list[dict[str, object]]], str],
        select_spreadsheet_text_column: Callable[[str, list[dict[str, object]], set[str] | None], str],
        detect_spreadsheet_text_filter: Callable[[str, list[dict[str, object]], set[str] | None], tuple[str, str]],
        filter_spreadsheet_rows_by_text_value: Callable[[list[dict[str, object]], str, str], list[dict[str, object]]],
        parse_spreadsheet_number: Callable[[object], float | None],
        format_spreadsheet_numeric: Callable[[float], str],
        select_spreadsheet_descriptor_column: Callable[[str, dict[str, object], str], str],
        fold_text: Callable[[str], str],
        tokenize: Callable[[str], set[str]],
    ) -> None:
        self._try_build_sheet_count_answer = try_build_sheet_count_answer
        self._try_build_date_lookup_answer = try_build_date_lookup_answer
        self._try_build_text_count_answer = try_build_text_count_answer
        self._try_build_text_list_answer = try_build_text_list_answer
        self._try_build_aggregate_answer = try_build_aggregate_answer
        self._try_build_row_answer = try_build_row_answer
        self._expand_spreadsheet_aggregate_docs = expand_spreadsheet_aggregate_docs
        self._load_scoped_context_docs = load_scoped_context_docs
        self._resolve_spreadsheet_sheet_hint = resolve_spreadsheet_sheet_hint
        self._extract_spreadsheet_structured_rows = extract_spreadsheet_structured_rows
        self._resolve_spreadsheet_aggregate_operation = resolve_spreadsheet_aggregate_operation
        self._apply_spreadsheet_aggregate_filters = apply_spreadsheet_aggregate_filters
        self._match_spreadsheet_column_by_hint = match_spreadsheet_column_by_hint
        self._select_spreadsheet_numeric_column = select_spreadsheet_numeric_column
        self._select_spreadsheet_text_column = select_spreadsheet_text_column
        self._detect_spreadsheet_text_filter = detect_spreadsheet_text_filter
        self._filter_spreadsheet_rows_by_text_value = filter_spreadsheet_rows_by_text_value
        self._parse_spreadsheet_number = parse_spreadsheet_number
        self._format_spreadsheet_numeric = format_spreadsheet_numeric
        self._select_spreadsheet_descriptor_column = select_spreadsheet_descriptor_column
        self._fold_text = fold_text
        self._tokenize = tokenize

    def try_generate_answer(
        self,
        *,
        raw_question: str,
        normalized_question: str,
        context_docs: list[Document],
        metadata_filter: dict[str, str | list[str]] | None,
    ) -> str:
        answer = self._try_build_sheet_count_answer(raw_question, context_docs)
        if answer:
            return answer

        answer = self._try_build_date_lookup_answer(raw_question, context_docs)
        if answer:
            return answer

        answer = self._try_build_text_count_answer(raw_question, context_docs, metadata_filter)
        if answer:
            return answer

        answer = self._try_build_text_list_answer(raw_question, context_docs, metadata_filter)
        if answer:
            return answer

        answer = self._try_build_advanced_table_answer(raw_question, context_docs, metadata_filter)
        if answer:
            return answer

        if normalized_question and normalized_question != raw_question:
            answer = self._try_build_advanced_table_answer(normalized_question, context_docs, metadata_filter)
            if answer:
                return answer

        answer = self._try_build_aggregate_answer(raw_question, context_docs, metadata_filter)
        if answer:
            return answer

        if normalized_question and normalized_question != raw_question:
            answer = self._try_build_aggregate_answer(normalized_question, context_docs, metadata_filter)
            if answer:
                return answer

        answer = self._try_build_row_answer(raw_question, context_docs)
        if answer:
            return answer

        if normalized_question and normalized_question != raw_question:
            answer = self._try_build_row_answer(normalized_question, context_docs)
            if answer:
                return answer

        return ""

    def _try_build_advanced_table_answer(
        self,
        question: str,
        context_docs: list[Document],
        metadata_filter: dict[str, str | list[str]] | None,
    ) -> str:
        folded_question = self._fold_text(question)
        if not folded_question:
            return ""
        if _TOPK_RETRIEVAL_TERM_RE.search(folded_question):
            return ""

        wants_compare = bool(_COMPARE_HINT_RE.search(folded_question))
        wants_group = bool(_GROUP_BY_HINT_RE.search(folded_question))
        wants_rank = bool(_TOP_BOTTOM_RE.search(folded_question))
        wants_filter = bool(_FILTER_ROW_HINT_RE.search(folded_question))
        if not any((wants_compare, wants_group, wants_rank, wants_filter)):
            return ""

        rows = self._collect_table_rows(question, context_docs, metadata_filter)
        if not rows:
            return ""

        if wants_compare:
            answer = self._try_build_compare_answer(question, folded_question, rows)
            if answer:
                return answer

        if wants_rank:
            answer = self._try_build_ranked_rows_answer(question, folded_question, rows)
            if answer:
                return answer

        if wants_group:
            answer = self._try_build_grouped_answer(question, folded_question, rows)
            if answer:
                return answer

        if wants_filter:
            answer = self._try_build_filtered_rows_answer(question, folded_question, rows)
            if answer:
                return answer

        return ""

    def _collect_table_rows(
        self,
        question: str,
        context_docs: list[Document],
        metadata_filter: dict[str, str | list[str]] | None,
    ) -> list[dict[str, object]]:
        scoped_docs = self._load_scoped_context_docs(metadata_filter)
        merged_docs = self._merge_docs(context_docs, scoped_docs)
        expanded_docs = self._expand_spreadsheet_aggregate_docs(merged_docs, metadata_filter)
        candidate_docs = self._merge_docs(merged_docs, expanded_docs)

        target_sheet = self._resolve_spreadsheet_sheet_hint(question, candidate_docs)
        rows = self._extract_spreadsheet_structured_rows(candidate_docs, target_sheet)
        rows.extend(self._extract_pipe_table_rows(candidate_docs))
        return self._deduplicate_rows(rows)

    def _try_build_grouped_answer(
        self,
        question: str,
        folded_question: str,
        rows: list[dict[str, object]],
    ) -> str:
        operation = self._resolve_metric_operation(folded_question)
        if not operation:
            return ""

        filtered_rows = self._apply_spreadsheet_aggregate_filters(rows, folded_question)
        if not filtered_rows:
            return ""

        numeric_column = ""
        if operation != "count":
            numeric_column = self._select_spreadsheet_numeric_column(folded_question, filtered_rows)
            if not numeric_column:
                return ""

        group_column = self._select_spreadsheet_text_column(
            question,
            filtered_rows,
            {numeric_column} if numeric_column else None,
        )
        if not group_column:
            hinted_column = self._extract_group_column_hint(folded_question)
            if hinted_column:
                group_column = self._match_spreadsheet_column_by_hint(filtered_rows, hinted_column)
        if not group_column:
            return ""

        grouped: dict[str, dict[str, object]] = {}
        for row in filtered_rows:
            values = row.get("values")
            if not isinstance(values, dict):
                continue

            group_value = str(values.get(group_column) or "").strip()
            if not group_value:
                continue

            payload = grouped.setdefault(group_value, {"rows": [], "numbers": []})
            payload["rows"].append(row)

            if operation == "count":
                continue

            numeric_value = self._parse_spreadsheet_number(values.get(numeric_column))
            if numeric_value is None:
                continue
            payload["numbers"].append(numeric_value)

        summaries: list[tuple[str, float, list[dict[str, object]]]] = []
        for group_value, payload in grouped.items():
            payload_rows = payload.get("rows")
            if not isinstance(payload_rows, list) or not payload_rows:
                continue

            if operation == "count":
                metric = float(len(payload_rows))
            else:
                numbers = payload.get("numbers")
                if not isinstance(numbers, list) or not numbers:
                    continue
                metric = self._reduce_metric(operation, numbers)
            summaries.append((group_value, metric, payload_rows))

        if not summaries:
            return ""

        summaries.sort(key=lambda item: item[1], reverse=operation != "min")
        label = {
            "sum": "tổng",
            "avg": "trung bình",
            "max": "cao nhất",
            "min": "thấp nhất",
            "count": "số lượng",
        }[operation]
        fragments = [
            (
                f"{group_value}: {self._format_spreadsheet_numeric(metric)}"
                f" (nguồn: {self._format_scope(payload_rows, numeric_column if operation != 'count' else group_column)})"
            )
            for group_value, metric, payload_rows in summaries[:6]
        ]

        if operation == "count":
            return f"Theo cột '{group_column}', {label} là: {'; '.join(fragments)}."
        return f"Theo cột '{group_column}', {label} của cột '{numeric_column}' là: {'; '.join(fragments)}."

    def _try_build_ranked_rows_answer(
        self,
        question: str,
        folded_question: str,
        rows: list[dict[str, object]],
    ) -> str:
        filtered_rows = self._apply_spreadsheet_aggregate_filters(rows, folded_question)
        if not filtered_rows:
            return ""

        numeric_column = self._select_spreadsheet_numeric_column(folded_question, filtered_rows)
        if not numeric_column:
            return ""

        direction, limit = self._resolve_rank_request(folded_question)
        numeric_rows: list[tuple[dict[str, object], float]] = []
        for row in filtered_rows:
            values = row.get("values")
            if not isinstance(values, dict):
                continue
            numeric_value = self._parse_spreadsheet_number(values.get(numeric_column))
            if numeric_value is None:
                continue
            numeric_rows.append((row, numeric_value))

        if not numeric_rows:
            return ""

        numeric_rows.sort(key=lambda item: item[1], reverse=direction == "desc")
        selected = numeric_rows[:limit]
        if not selected:
            return ""

        fragments: list[str] = []
        for row, numeric_value in selected:
            values = row.get("values")
            if not isinstance(values, dict):
                continue

            descriptor_column = self._select_spreadsheet_descriptor_column(question, values, numeric_column)
            descriptor_value = str(values.get(descriptor_column) or "").strip() if descriptor_column else ""

            if descriptor_column and descriptor_value:
                label = f"{descriptor_column} {descriptor_value}"
            else:
                row_number = int(row.get("row_number", 0) or 0)
                label = f"dòng {row_number}" if row_number > 0 else "dòng phù hợp"

            result_fragment = self._extract_result_fragment(values)
            value_fragment = f"{label}: {self._format_spreadsheet_numeric(numeric_value)}"
            if result_fragment:
                value_fragment = f"{value_fragment}; {result_fragment}"

            fragments.append(
                f"{value_fragment} (nguồn: {self._format_scope([row], numeric_column)})"
            )

        if not fragments:
            return ""

        if limit == 1:
            prefix = "Giá trị cao nhất" if direction == "desc" else "Giá trị thấp nhất"
        else:
            prefix = f"Top {limit}" if direction == "desc" else f"Bottom {limit}"
        return f"{prefix} theo cột '{numeric_column}': {'; '.join(fragments)}."

    def _extract_result_fragment(self, values: dict[str, object]) -> str:
        for column, raw_value in values.items():
            label = str(column or "").strip()
            value = str(raw_value or "").strip()
            if not label or not value:
                continue
            folded_label = self._fold_text(label)
            if re.search(r"\b(ket\s*qua|result|status|pass|fail)\b", folded_label) or label in {"結果", "合否"}:
                return f"{label}: {value}"
        return ""

    def _try_build_compare_answer(
        self,
        question: str,
        folded_question: str,
        rows: list[dict[str, object]],
    ) -> str:
        filtered_rows = self._apply_spreadsheet_aggregate_filters(rows, folded_question)
        if not filtered_rows:
            return ""

        operation = self._resolve_metric_operation(folded_question) or "sum"
        numeric_column = ""
        if operation != "count":
            numeric_column = self._select_spreadsheet_numeric_column(folded_question, filtered_rows)
            if not numeric_column:
                return ""

        compare_column, compare_values = self._identify_compare_dimension(
            folded_question,
            filtered_rows,
            {numeric_column} if numeric_column else None,
        )
        if not compare_column or len(compare_values) < 2:
            return ""

        fragments: list[str] = []
        metrics: list[float] = []
        for compare_value in compare_values[:3]:
            matched_rows = self._filter_spreadsheet_rows_by_text_value(filtered_rows, compare_column, compare_value)
            if not matched_rows:
                continue

            if operation == "count":
                metric = float(len(matched_rows))
            else:
                numeric_values: list[float] = []
                for row in matched_rows:
                    values = row.get("values")
                    if not isinstance(values, dict):
                        continue
                    numeric_value = self._parse_spreadsheet_number(values.get(numeric_column))
                    if numeric_value is not None:
                        numeric_values.append(numeric_value)
                if not numeric_values:
                    continue
                metric = self._reduce_metric(operation, numeric_values)

            metrics.append(metric)
            fragments.append(
                f"{compare_value}: {self._format_spreadsheet_numeric(metric)}"
                f" (nguồn: {self._format_scope(matched_rows, numeric_column if operation != 'count' else compare_column)})"
            )

        if len(fragments) < 2:
            return ""

        if len(metrics) >= 2:
            difference = self._format_spreadsheet_numeric(abs(metrics[0] - metrics[1]))
            suffix = f" Chênh lệch: {difference}."
        else:
            suffix = ""

        if operation == "count":
            return f"So sánh theo cột '{compare_column}': {'; '.join(fragments)}.{suffix}".strip()
        return f"So sánh cột '{numeric_column}' theo '{compare_column}': {'; '.join(fragments)}.{suffix}".strip()

    def _try_build_filtered_rows_answer(
        self,
        question: str,
        folded_question: str,
        rows: list[dict[str, object]],
    ) -> str:
        filtered_rows = self._apply_spreadsheet_aggregate_filters(rows, folded_question)
        if not filtered_rows:
            return ""

        filter_column, filter_value = self._detect_spreadsheet_text_filter(question, filtered_rows, None)
        if not filter_column or not filter_value:
            return ""

        matched_rows = self._filter_spreadsheet_rows_by_text_value(filtered_rows, filter_column, filter_value)
        if not matched_rows:
            return ""

        display_column = self._select_spreadsheet_text_column(question, matched_rows, {filter_column})
        fragments: list[str] = []
        seen: set[str] = set()
        for row in matched_rows[:5]:
            values = row.get("values")
            if not isinstance(values, dict):
                continue

            if display_column:
                display_value = str(values.get(display_column) or "").strip()
                if not display_value:
                    continue
                dedup_key = self._fold_text(display_value)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                fragments.append(
                    f"{display_column} {display_value} (nguồn: {self._format_scope([row], display_column)})"
                )
                continue

            display_parts: list[str] = []
            for column, raw_value in values.items():
                if self._fold_text(column) == self._fold_text(filter_column):
                    continue
                value_text = str(raw_value or "").strip()
                if not value_text:
                    continue
                display_parts.append(f"{column}: {value_text}")
                if len(display_parts) >= 2:
                    break

            if not display_parts:
                continue
            row_signature = " | ".join(display_parts)
            if row_signature in seen:
                continue
            seen.add(row_signature)
            fragments.append(f"{row_signature} (nguồn: {self._format_scope([row], filter_column)})")

        if not fragments:
            return ""

        return f"Các dòng có {filter_column} '{filter_value}': {'; '.join(fragments)}."

    def _extract_pipe_table_rows(self, docs: list[Document]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        seen: set[str] = set()

        for doc_index, doc in enumerate(docs, start=1):
            metadata = doc.metadata
            source = str(metadata.get("source") or "").strip()
            sheet_name = str(metadata.get("sheet_name") or metadata.get("sheet") or "").strip()
            page_number = self._coerce_int(metadata.get("page_number") or metadata.get("page"))
            slide_number = self._coerce_int(metadata.get("slide_number") or metadata.get("slide"))

            slide_blocks = metadata.get("slide_blocks")
            if isinstance(slide_blocks, list):
                for block_index, block in enumerate(slide_blocks, start=1):
                    if not isinstance(block, dict):
                        continue
                    if str(block.get("block_type") or "").lower() != "table":
                        continue
                    block_content = str(block.get("content") or "").strip()
                    if not block_content:
                        continue
                    rows.extend(
                        self._parse_pipe_table_text(
                            text=block_content,
                            source=source,
                            sheet_name=sheet_name,
                            table_name=f"slide_table_{block_index}",
                            page_number=page_number,
                            slide_number=slide_number,
                            seen=seen,
                        )
                    )

            rows.extend(
                self._parse_pipe_table_text(
                    text=str(doc.page_content or ""),
                    source=source,
                    sheet_name=sheet_name,
                    table_name=str(metadata.get("table_name") or f"parsed_table_{doc_index}"),
                    page_number=page_number,
                    slide_number=slide_number,
                    seen=seen,
                )
            )

        return rows

    def _parse_pipe_table_text(
        self,
        *,
        text: str,
        source: str,
        sheet_name: str,
        table_name: str,
        page_number: int,
        slide_number: int,
        seen: set[str],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for group_index, group in enumerate(self._extract_pipe_table_groups(text), start=1):
            if len(group) < 2:
                continue

            headers = [cell.strip() for cell in group[0] if cell.strip()]
            if len(headers) < 2:
                continue

            for row_index, raw_cells in enumerate(group[1:], start=2):
                values: OrderedDict[str, str] = OrderedDict()
                for header, cell in zip(headers, raw_cells):
                    label = str(header or "").strip()
                    value_text = str(cell or "").strip()
                    if not label or not value_text:
                        continue
                    values[label] = value_text

                if not values:
                    continue

                row_payload = {
                    "source": source,
                    "sheet_name": sheet_name,
                    "row_number": row_index,
                    "table_name": table_name if table_name else f"parsed_table_{group_index}",
                    "row_range": str(row_index),
                    "page_number": page_number,
                    "slide_number": slide_number,
                    "values": values,
                }
                dedup_key = self._row_dedup_key(row_payload)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                rows.append(row_payload)

        return rows

    @staticmethod
    def _extract_pipe_table_groups(text: str) -> list[list[list[str]]]:
        groups: list[list[list[str]]] = []
        current_group: list[list[str]] = []

        for line in str(text or "").splitlines():
            cells = TableQueryService._parse_pipe_cells(line)
            if cells:
                if current_group and len(cells) != len(current_group[0]):
                    if len(current_group) >= 2:
                        groups.append(current_group)
                    current_group = [cells]
                else:
                    current_group.append(cells)
                continue

            if len(current_group) >= 2:
                groups.append(current_group)
            current_group = []

        if len(current_group) >= 2:
            groups.append(current_group)
        return groups

    @staticmethod
    def _parse_pipe_cells(line: str) -> list[str]:
        candidate = str(line or "").strip()
        if not candidate:
            return []

        if ":" in candidate:
            prefix, suffix = candidate.split(":", 1)
            if suffix.count("|") >= 1 and prefix.count("|") == 0:
                candidate = suffix.strip()

        candidate = candidate.strip("- ").strip()
        if candidate.count("|") < 1:
            return []

        cells = [cell.strip() for cell in candidate.split("|")]
        while cells and not cells[0]:
            cells.pop(0)
        while cells and not cells[-1]:
            cells.pop()
        if len([cell for cell in cells if cell]) < 2:
            return []
        if all(re.fullmatch(r"[-=]{2,}", cell or "") for cell in cells if cell):
            return []
        return cells

    def _identify_compare_dimension(
        self,
        folded_question: str,
        rows: list[dict[str, object]],
        excluded_columns: set[str] | None,
    ) -> tuple[str, list[str]]:
        excluded = {self._fold_text(column) for column in excluded_columns or set() if str(column).strip()}
        best_column = ""
        best_values: list[str] = []
        best_score = 0.0

        for row in rows:
            values = row.get("values")
            if not isinstance(values, dict):
                continue

            for column in values:
                folded_column = self._fold_text(column)
                if not folded_column or folded_column in excluded:
                    continue

                candidates = self._collect_distinct_column_values(rows, str(column))
                matched: list[tuple[int, str]] = []
                for original_value, folded_value in candidates:
                    if len(folded_value) < 2:
                        continue
                    position = folded_question.find(folded_value)
                    if position < 0:
                        continue
                    matched.append((position, original_value))

                if len(matched) < 2:
                    continue

                matched.sort(key=lambda item: item[0])
                score = float(len(matched) * 3)
                if folded_column in folded_question:
                    score += 1.0
                if score <= best_score:
                    continue

                best_score = score
                best_column = str(column)
                best_values = [value for _, value in matched]

        return best_column, best_values

    def _collect_distinct_column_values(self, rows: list[dict[str, object]], column: str) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            payload = row.get("values")
            if not isinstance(payload, dict):
                continue

            raw_value = str(payload.get(column) or "").strip()
            folded_value = self._fold_text(raw_value)
            if not raw_value or not folded_value or folded_value in seen:
                continue
            seen.add(folded_value)
            values.append((raw_value, folded_value))
        return values

    def _resolve_metric_operation(self, folded_question: str) -> str:
        aggregate_operation = self._resolve_spreadsheet_aggregate_operation(folded_question)
        if aggregate_operation:
            return aggregate_operation
        if _COUNT_HINT_RE.search(folded_question):
            return "count"
        return ""

    @staticmethod
    def _reduce_metric(operation: str, numbers: list[float]) -> float:
        if operation == "sum":
            return float(sum(numbers))
        if operation == "avg":
            return float(sum(numbers) / max(1, len(numbers)))
        if operation == "max":
            return float(max(numbers))
        if operation == "min":
            return float(min(numbers))
        return float(sum(numbers))

    @staticmethod
    def _resolve_rank_request(folded_question: str) -> tuple[str, int]:
        match = _TOP_BOTTOM_RE.search(folded_question)
        if match is None:
            return "desc", 3

        keyword = str(match.group(1) or "").lower()
        amount = int(match.group(2) or 0)
        direction = "desc"
        if keyword == "bottom" or re.search(r"\b(thap|thấp|nho|nhỏ|it|ít)\b", folded_question):
            direction = "asc"
        if amount <= 0:
            amount = 1
        return direction, min(10, max(1, amount))

    def _extract_group_column_hint(self, folded_question: str) -> str:
        match = re.search(r"\b(?:group\s*by|theo|per)\s+([\w\sà-ỹ]+)", folded_question, re.IGNORECASE)
        if match is None:
            return ""
        hint = re.split(r"\b(sum|tong|tổng|avg|average|trung\s*binh|trung\s*bình|max|min|count|bao\s*nhieu|bao\s*nhiêu)\b", match.group(1), maxsplit=1)[0]
        return re.sub(r"\s+", " ", hint).strip()

    def _format_scope(self, rows: list[dict[str, object]], column: str) -> str:
        source_values = {
            Path(str(row.get("source") or "")).name or str(row.get("source") or "").strip()
            for row in rows
            if str(row.get("source") or "").strip()
        }
        sheet_values = {str(row.get("sheet_name") or "").strip() for row in rows if str(row.get("sheet_name") or "").strip()}
        table_values = {str(row.get("table_name") or "").strip() for row in rows if str(row.get("table_name") or "").strip()}
        slide_values = {int(row.get("slide_number") or 0) for row in rows if int(row.get("slide_number") or 0) > 0}
        page_values = {int(row.get("page_number") or 0) for row in rows if int(row.get("page_number") or 0) > 0}

        parts: list[str] = []
        if len(source_values) == 1:
            parts.append(next(iter(source_values)))
        elif source_values:
            parts.append("nhiều nguồn")

        if len(sheet_values) == 1:
            parts.append(f"sheet {next(iter(sheet_values))}")
        elif len(slide_values) == 1:
            parts.append(f"slide {next(iter(slide_values))}")
        elif len(page_values) == 1:
            parts.append(f"trang {next(iter(page_values))}")

        if len(table_values) == 1:
            parts.append(f"table {next(iter(table_values))}")

        row_span = self._summarize_row_span(rows)
        if row_span:
            parts.append(f"rows {row_span}")
        if column:
            parts.append(f"cột {column}")

        return "; ".join(parts) if parts else column

    @staticmethod
    def _summarize_row_span(rows: list[dict[str, object]]) -> str:
        row_numbers = sorted({int(row.get("row_number") or 0) for row in rows if int(row.get("row_number") or 0) > 0})
        if row_numbers:
            if len(row_numbers) == 1:
                return str(row_numbers[0])
            return f"{row_numbers[0]}:{row_numbers[-1]}"

        row_ranges = [str(row.get("row_range") or "").strip() for row in rows if str(row.get("row_range") or "").strip()]
        if not row_ranges:
            return ""
        unique_ranges: list[str] = []
        for item in row_ranges:
            if item not in unique_ranges:
                unique_ranges.append(item)
        return ", ".join(unique_ranges[:3])

    @staticmethod
    def _coerce_int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _merge_docs(self, first: list[Document], second: list[Document]) -> list[Document]:
        merged: list[Document] = []
        seen: set[str] = set()
        for doc in [*first, *second]:
            key = self._document_dedup_key(doc)
            if key in seen:
                continue
            seen.add(key)
            merged.append(doc)
        return merged

    def _document_dedup_key(self, doc: Document) -> str:
        metadata = doc.metadata
        source = str(metadata.get("source") or "")
        sheet_name = str(metadata.get("sheet_name") or metadata.get("sheet") or "")
        page_number = str(metadata.get("page_number") or metadata.get("page") or "")
        slide_number = str(metadata.get("slide_number") or metadata.get("slide") or "")
        content = self._fold_text(str(doc.page_content or "")[:2000])
        return f"{source}|{sheet_name}|{page_number}|{slide_number}|{content}"

    def _deduplicate_rows(self, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        deduplicated: list[dict[str, object]] = []
        seen: set[str] = set()
        for row in rows:
            dedup_key = self._row_dedup_key(row)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            deduplicated.append(row)
        return deduplicated

    @staticmethod
    def _row_dedup_key(row: dict[str, object]) -> str:
        values = row.get("values")
        fingerprint = json.dumps(values, ensure_ascii=False, sort_keys=True) if isinstance(values, dict) else ""
        return "|".join(
            [
                str(row.get("source") or ""),
                str(row.get("sheet_name") or ""),
                str(row.get("table_name") or ""),
                str(row.get("row_number") or ""),
                fingerprint,
            ]
        )
