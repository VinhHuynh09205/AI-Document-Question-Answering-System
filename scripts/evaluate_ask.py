import argparse
import json
import re
import statistics
import time
from collections.abc import Iterable
from pathlib import Path

import httpx


def load_cases(file_path: Path) -> list[dict[str, object]]:
    raw_text = file_path.read_text(encoding="utf-8")
    stripped = raw_text.strip()
    if not stripped:
        return []

    if file_path.suffix.lower() == ".json":
        payload = json.loads(raw_text)
        if isinstance(payload, list):
            return [case for case in payload if isinstance(case, dict)]
        raise ValueError("JSON case file must contain a top-level list")

    cases: list[dict[str, object]] = []
    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        payload = json.loads(stripped_line)
        if not isinstance(payload, dict):
            raise ValueError(f"Line {line_number} must be a JSON object")
        cases.append(payload)
    return cases


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _fold_text(value: object) -> str:
    return _normalize_text(value).casefold()


def _to_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float, bool)):
        text = _normalize_text(value)
        return [text] if text else []
    if isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
        items: list[str] = []
        for item in value:
            text = _normalize_text(item)
            if text:
                items.append(text)
        return items
    text = _normalize_text(value)
    return [text] if text else []


def _contains_text(haystack: str, needle: str) -> bool:
    return bool(needle) and _fold_text(needle) in _fold_text(haystack)


def _collect_sources(response_payload: dict[str, object]) -> list[str]:
    raw_sources = response_payload.get("sources")
    if not isinstance(raw_sources, list):
        return []
    return [_normalize_text(item) for item in raw_sources if _normalize_text(item)]


def _build_observable_text(answer: str, sources: list[str]) -> str:
    return "\n".join(part for part in [answer, *sources] if _normalize_text(part))


def _expected_context_found(case: dict[str, object]) -> bool:
    if "expected_context_found" in case:
        return bool(case.get("expected_context_found"))
    return bool(case.get("require_context_found", True))


def _location_candidates(field_name: str, value: object) -> list[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return []

    if field_name == "expected_page":
        return [f"page {normalized}", f"trang {normalized}", f"p. {normalized}", normalized]
    if field_name == "expected_slide":
        return [f"slide {normalized}", normalized]
    if field_name == "expected_sheet":
        return [f"sheet {normalized}", normalized]
    if field_name == "expected_table":
        return [f"table {normalized}", normalized]
    if field_name == "expected_row_span":
        return [f"rows {normalized}", f"row {normalized}", f"dòng {normalized}", f"dong {normalized}", normalized]
    return [normalized]


def evaluate_case(case: dict[str, object], response_payload: dict[str, object]) -> list[str]:
    failures: list[str] = []
    answer = _normalize_text(response_payload.get("answer") or "")
    sources = _collect_sources(response_payload)
    context_found = bool(response_payload.get("context_found"))
    observable_text = _build_observable_text(answer, sources)

    if context_found != _expected_context_found(case):
        failures.append(f"context_found_mismatch:expected={_expected_context_found(case)} actual={context_found}")

    expected_answer = _normalize_text(case.get("expected_answer") or "")
    if expected_answer and _fold_text(answer) != _fold_text(expected_answer):
        failures.append("answer_exact_mismatch")

    for text in _to_string_list(case.get("expected_answer_contains")):
        if not _contains_text(answer, text):
            failures.append(f"missing_answer_substring:{text}")

    expected_substrings = case.get("expected_substrings")
    if isinstance(expected_substrings, list):
        for item in expected_substrings:
            text = _normalize_text(item)
            if text and not _contains_text(answer, text):
                failures.append(f"missing_answer_substring:{text}")

    expected_any_groups = case.get("expected_any_substrings")
    if isinstance(expected_any_groups, list):
        for group in expected_any_groups:
            if not isinstance(group, list):
                continue
            candidates = [text for text in _to_string_list(group) if text]
            if candidates and not any(_contains_text(answer, candidate) for candidate in candidates):
                failures.append(f"missing_any_answer_group:{'|'.join(candidates)}")

    forbidden_substrings = case.get("forbidden_substrings")
    if isinstance(forbidden_substrings, list):
        for item in forbidden_substrings:
            text = _normalize_text(item)
            if text and _contains_text(answer, text):
                failures.append(f"forbidden_answer_substring:{text}")

    min_sources = int(case.get("min_sources", 0) or 0)
    if len(sources) < min_sources:
        failures.append(f"min_sources:{min_sources}")

    expected_sources = _to_string_list(case.get("expected_source"))
    expected_sources.extend(_to_string_list(case.get("expected_sources")))
    deduped_expected_sources: list[str] = []
    for item in expected_sources:
        if item not in deduped_expected_sources:
            deduped_expected_sources.append(item)
    for expected_source in deduped_expected_sources:
        if not any(_contains_text(source, expected_source) for source in sources):
            failures.append(f"missing_source_substring:{expected_source}")

    for expected_file_type in _to_string_list(case.get("expected_file_type")):
        if not _contains_text(observable_text, expected_file_type):
            failures.append(f"missing_file_type:{expected_file_type}")

    for field_name in [
        "expected_page",
        "expected_slide",
        "expected_sheet",
        "expected_table",
        "expected_row_span",
    ]:
        value = case.get(field_name)
        candidates = _location_candidates(field_name, value)
        if not candidates:
            continue
        if not any(_contains_text(observable_text, candidate) for candidate in candidates):
            failures.append(f"missing_{field_name}:{_normalize_text(value)}")

    return failures


def run_evaluation(
    *,
    base_url: str,
    endpoint: str,
    cases: list[dict[str, object]],
    timeout: float,
    output_path: Path | None,
) -> int:
    results: list[dict[str, object]] = []
    latencies_ms: list[float] = []
    executed = 0
    passed = 0
    skipped = 0

    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        for index, case in enumerate(cases, start=1):
            case_id = str(case.get("id") or f"case-{index}")
            tags = case.get("tags") if isinstance(case.get("tags"), list) else []
            notes = _normalize_text(case.get("notes") or "")

            if case.get("enabled") is False:
                skipped += 1
                results.append(
                    {
                        "id": case_id,
                        "enabled": False,
                        "skipped": True,
                        "tags": tags,
                        "notes": notes,
                    }
                )
                print(f"SKIP {case_id}: disabled template case")
                continue

            question = str(case.get("question") or "").strip()
            if not question:
                raise ValueError(f"Case #{index} is missing question")

            executed += 1

            payload: dict[str, object] = {"question": question}
            metadata_filter = case.get("metadata_filter")
            if isinstance(metadata_filter, dict):
                payload["metadata_filter"] = metadata_filter

            started_at = time.perf_counter()
            response = client.post(endpoint, json=payload)
            latency_ms = (time.perf_counter() - started_at) * 1000.0
            latencies_ms.append(latency_ms)

            result: dict[str, object] = {
                "id": case_id,
                "question": question,
                "enabled": True,
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 2),
                "tags": tags,
                "notes": notes,
                "metadata_filter": metadata_filter if isinstance(metadata_filter, dict) else None,
            }

            if response.status_code != 200:
                result["passed"] = False
                result["failures"] = [f"http_status:{response.status_code}"]
                result["response_text"] = response.text[:2000]
                results.append(result)
                print(f"FAIL {case_id}: http_status={response.status_code}")
                continue

            try:
                response_payload = response.json()
            except ValueError:
                response_payload = None
            if not isinstance(response_payload, dict):
                result["passed"] = False
                result["failures"] = ["invalid_json_payload"]
                results.append(result)
                print(f"FAIL {case_id}: invalid_json_payload")
                continue

            failures = evaluate_case(case, response_payload)
            result["passed"] = not failures
            result["failures"] = failures
            result["answer"] = str(response_payload.get("answer") or "")
            result["sources"] = response_payload.get("sources") if isinstance(response_payload.get("sources"), list) else []
            result["context_found"] = bool(response_payload.get("context_found"))
            results.append(result)

            if failures:
                print(f"FAIL {case_id}: {', '.join(failures)}")
                continue

            passed += 1
            print(f"PASS {case_id}: {latency_ms:.2f} ms")

    summary = {
        "total_cases": len(cases),
        "executed_cases": executed,
        "skipped_cases": skipped,
        "passed": passed,
        "failed": max(0, executed - passed),
        "pass_rate": round((passed / executed), 4) if executed else 0.0,
        "mean_latency_ms": round(statistics.mean(latencies_ms), 2) if latencies_ms else 0.0,
        "p50_latency_ms": round(statistics.median(latencies_ms), 2) if latencies_ms else 0.0,
        "max_latency_ms": round(max(latencies_ms), 2) if latencies_ms else 0.0,
        "results": results,
    }

    print(f"Summary: passed={passed} failed={summary['failed']} skipped={skipped} executed={executed}")
    if latencies_ms:
        print(f"Mean latency (ms): {summary['mean_latency_ms']:.2f}")
        print(f"P50 latency (ms): {summary['p50_latency_ms']:.2f}")
        print(f"Max latency (ms): {summary['max_latency_ms']:.2f}")

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report written to {output_path}")

    return 0 if executed > 0 and summary["failed"] == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate /ask endpoint with golden cases")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--endpoint", default="/api/v1/ask")
    parser.add_argument("--cases", required=True, help="Path to JSON or JSONL evaluation cases")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", help="Optional path to write JSON report")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    if not cases:
        raise ValueError("No evaluation cases found")

    raise SystemExit(
        run_evaluation(
            base_url=args.base_url,
            endpoint=args.endpoint,
            cases=cases,
            timeout=max(1.0, args.timeout),
            output_path=Path(args.output) if args.output else None,
        )
    )


if __name__ == "__main__":
    main()