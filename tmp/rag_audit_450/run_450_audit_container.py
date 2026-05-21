from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import statistics
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


def load_module(name: str, path: str):
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def score_value(item: dict[str, Any]) -> float:
    try:
        return float(item.get("evaluation", {}).get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def current_case_from_old(old_case: dict[str, Any], profile_by_name: dict[str, Any]) -> dict[str, Any] | None:
    names = list(old_case.get("files") or [])
    profiles = [profile_by_name.get(name) for name in names]
    if not profiles or any(profile is None for profile in profiles):
        return None
    case = dict(old_case)
    case["selected_document_ids"] = [profile.document_id for profile in profiles if profile is not None]
    return case


def row_expected_terms(values: dict[str, Any], limit: int = 6) -> list[str]:
    terms: list[str] = []
    for value in values.values():
        text = str(value or "").strip()
        if text:
            terms.append(text)
        if len(terms) >= limit:
            break
    return terms


def clone_case(case: dict[str, Any], prefix: str, group: str | None = None) -> dict[str, Any]:
    cloned = dict(case)
    cloned["id"] = f"{prefix}-{case.get('id', 'CASE')}"
    if group:
        cloned["group"] = group
    return cloned


def build_focused_cases(
    audit: Any,
    raw_results_path: Path,
    profile_by_name: dict[str, Any],
    max_focused: int,
) -> list[dict[str, Any]]:
    raw_payload = json.loads(raw_results_path.read_text(encoding="utf-8"))
    raw_results = list(raw_payload.get("results") or [])
    group_order = {
        "Negative/Hallucination": 0,
        "Table/Numeric": 1,
        "Slide/Presentation": 2,
        "OCR/Vision": 3,
        "Comparison": 4,
        "Direct": 5,
        "Summary": 6,
    }
    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "None": 4}
    focused: list[tuple[tuple[int, int, float, str], dict[str, Any]]] = []
    seen_ids: set[str] = set()
    for item in raw_results:
        case = item.get("case") or {}
        group = str(case.get("group") or "")
        score = score_value(item)
        if score < 1.0 or group in {"Negative/Hallucination", "Table/Numeric", "Slide/Presentation"}:
            current_case = current_case_from_old(case, profile_by_name)
            if current_case is None:
                continue
            case_id = str(current_case.get("id") or "")
            if case_id in seen_ids:
                continue
            seen_ids.add(case_id)
            severity = str((item.get("evaluation") or {}).get("severity") or "None")
            priority = (
                group_order.get(group, 9),
                severity_order.get(severity, 9),
                score,
                case_id,
            )
            focused.append((priority, clone_case(current_case, "F105", "Focused Regression")))
    focused.sort(key=lambda item: item[0])
    return [case for _, case in focused[:max_focused]]


def build_extra_40(postfix: Any, audit: Any, profiles: list[Any]) -> list[dict[str, Any]]:
    return [clone_case(case, "E40", "Postfix Extra") for case in postfix.build_extra_cases(audit, profiles)]


def build_extra_45(audit: Any, profiles: list[Any]) -> list[dict[str, Any]]:
    profile_by_name = {profile.original_name: profile for profile in profiles}
    cases: list[dict[str, Any]] = []

    def add(case: dict[str, Any]) -> None:
        if len(cases) >= 45:
            return
        case = clone_case(case, f"N45-{len(cases) + 1:03d}", "Additional 45")
        cases.append(case)

    rich_profiles = sorted(profiles, key=lambda profile: profile.chunk_count, reverse=True)
    for profile in rich_profiles[:10]:
        line = profile.lines[1] if len(profile.lines) > 1 else profile.title
        terms = audit.extract_keywords(line, limit=6) or profile.terms[:6]
        add(
            audit.make_case(
                "DETAIL",
                "Additional 45",
                [profile],
                f'Trong file "{profile.original_name}", chi tiet nao lien quan den "{terms[0] if terms else profile.title}"?',
                line or profile.title,
                terms,
            )
        )

    for profile in rich_profiles[10:18]:
        add(
            audit.make_case(
                "SUMMARY",
                "Additional 45",
                [profile],
                f'Tom tat ngan file "{profile.original_name}" thanh 2 y chinh.',
                profile.title,
                profile.terms[:6],
            )
        )

    negative_topics = [
        "mat khau wifi noi bo",
        "so CCCD cua sinh vien",
        "API key bi mat",
        "luong nhan vien",
        "so tai khoan ngan hang",
        "ma OTP dang nhap",
        "gia co phieu Tesla",
        "ho so benh an",
    ]
    negative_profiles = sorted(profiles, key=lambda profile: profile.original_name.lower())[: len(negative_topics)]
    for profile, topic in zip(negative_profiles, negative_topics):
        add(
            audit.make_case(
                "NEG",
                "Additional 45",
                [profile],
                f'Trong file "{profile.original_name}" co thong tin ve {topic} khong?',
                "Khong tim thay thong tin trong tai lieu.",
                ["khong", "khong tim thay", "khong co thong tin"],
                kind="negative",
                forbidden_terms=[topic],
            )
        )

    image_profiles = [p for p in profiles if p.file_type in {"PNG", "JPG", "JPEG"}]
    for profile in image_profiles[:7]:
        add(
            audit.make_case(
                "OCR",
                "Additional 45",
                [profile],
                f'Anh "{profile.original_name}" co cac tu khoa noi bat nao?',
                profile.title,
                profile.terms[:6] or audit.extract_keywords(profile.text, limit=6),
            )
        )

    table_added = 0
    for profile in [p for p in profiles if p.file_type in {"XLSX", "XLS"}]:
        rows = audit.structured_rows_from_profile(profile)
        for sheet, row_number, values in rows[:2]:
            if table_added >= 6:
                break
            expected = "; ".join(f"{key}: {value}" for key, value in list(values.items())[:6])
            add(
                audit.make_case(
                    "TABLE",
                    "Additional 45",
                    [profile],
                    f'Trong workbook "{profile.original_name}", sheet "{sheet}", dong {row_number} gom thong tin gi?',
                    expected,
                    row_expected_terms(values),
                )
            )
            table_added += 1
        if table_added >= 6:
            break

    slide_added = 0
    for profile in [p for p in profiles if p.file_type == "PPTX"]:
        seen: set[int] = set()
        for doc in profile.chunks:
            try:
                slide_number = int(doc.metadata.get("slide_number") or doc.metadata.get("slide") or 0)
            except (TypeError, ValueError):
                continue
            if slide_number <= 0 or slide_number in seen:
                continue
            seen.add(slide_number)
            terms = audit.extract_keywords(doc.page_content, limit=6) or profile.terms[:6]
            expected = "; ".join(audit.useful_lines(doc.page_content, max_lines=3)) or profile.title
            add(
                audit.make_case(
                    "SLIDE",
                    "Additional 45",
                    [profile],
                    f'Slide {slide_number} trong file "{profile.original_name}" co noi dung chinh gi?',
                    expected,
                    terms,
                )
            )
            slide_added += 1
            if slide_added >= 6:
                break
        if slide_added >= 6:
            break

    comparison_pairs = [
        ("pdf_02_an_toan_du_lieu.pdf", "bao_cao_an_toan_du_lieu_ca_nhan.docx"),
        ("txt_02_ke_hoach_clb_sach.txt", "docx_02_ca_phe_sach.docx"),
        ("png_02_quy_trinh_giao_hang.png", "xlsx_02_ke_hoach_hoc_tap.xlsx"),
    ]
    for left_name, right_name in comparison_pairs:
        left = profile_by_name.get(left_name)
        right = profile_by_name.get(right_name)
        if left is None or right is None:
            continue
        add(
            audit.make_case(
                "COMPARE",
                "Additional 45",
                [left, right],
                f'So sanh ngan "{left_name}" voi "{right_name}".',
                f"Can nhac den ca hai file: {left.title}; {right.title}",
                (left.terms[:3] + right.terms[:3])[:8],
            )
        )

    if len(cases) != 45:
        raise RuntimeError(f"Expected 45 additional cases, got {len(cases)}")
    return cases


def run_case(audit: Any, container: Any, username: str, chat_id: str, case: dict[str, Any]) -> dict[str, Any]:
    latency, answer, sources = audit.ask_case(container, username, chat_id, case)
    evaluation = audit.evaluate_case(case, answer, sources)
    return {
        "ID": case["id"],
        "Run": case.get("run") or case.get("group") or "",
        "File": ", ".join(case["files"]),
        "FileType": case["file_type"],
        "Group": case["group"],
        "Question": case["question"],
        "Expected": case["expected_answer"],
        "Actual": evaluation["actual_answer"],
        "Sources": evaluation["sources"],
        "Retrieval": evaluation["retrieval"],
        "Citation": evaluation["citation"],
        "Answer": evaluation["answer_status"],
        "Score": evaluation["score"],
        "Hallucination": evaluation["hallucination"],
        "Severity": evaluation["severity"],
        "Notes": evaluation["notes"],
        "Fix": evaluation["fix"],
        "LatencyMs": round(latency * 1000, 2),
    }


def is_yes(value: Any) -> bool:
    text = str(value or "")
    return text in {"Dung", "Đúng", "ÄÃºng"} or text.startswith("Đ") or text.startswith("Ä")


def summarize(rows: list[dict[str, Any]], total_files: int) -> OrderedDict[str, Any]:
    total = len(rows)
    full = sum(1 for row in rows if float(row["Score"]) == 1.0)
    partial = sum(1 for row in rows if float(row["Score"]) == 0.5)
    fail = sum(1 for row in rows if float(row["Score"]) == 0.0)
    retrieval = sum(1 for row in rows if is_yes(row["Retrieval"]))
    citation = sum(1 for row in rows if is_yes(row["Citation"]))
    hallucination = sum(1 for row in rows if str(row["Hallucination"]).lower() in {"co", "có", "yes", "true"} or str(row["Hallucination"]).startswith("C"))
    latencies = [float(row["LatencyMs"]) for row in rows if row.get("LatencyMs") not in {"", None}]
    accepted = full + partial
    return OrderedDict(
        [
            ("total_files", total_files),
            ("total_questions", total),
            ("full_correct", full),
            ("partial_correct", partial),
            ("fail", fail),
            ("full_accuracy", round(full / max(1, total), 4)),
            ("accepted_count", accepted),
            ("accepted_rate", round(accepted / max(1, total), 4)),
            ("retrieval_correct", retrieval),
            ("retrieval_rate", round(retrieval / max(1, total), 4)),
            ("citation_correct", citation),
            ("citation_rate", round(citation / max(1, total), 4)),
            ("hallucination_count", hallucination),
            ("hallucination_rate", round(hallucination / max(1, total), 4)),
            ("mean_latency_ms", round(statistics.mean(latencies), 2) if latencies else None),
        ]
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, summary: OrderedDict[str, Any], rows: list[dict[str, Any]]) -> None:
    failed = [row for row in rows if float(row["Score"]) < 1.0 or not is_yes(row["Retrieval"]) or not is_yes(row["Citation"]) or str(row["Hallucination"]).startswith("C")]
    by_group = Counter(str(row["Group"]) for row in rows)
    lines = [
        "# Unified 450-Question Audit",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Question Groups", "", "| Group | Count |", "|---|---:|"])
    for group, count in sorted(by_group.items()):
        lines.append(f"| {group} | {count} |")
    lines.extend(["", "## Cases To Review", "", "| ID | File | Score | Retrieval | Citation | Hallucination | Notes |", "|---|---|---:|---|---|---|---|"])
    for row in failed[:80]:
        notes = str(row["Notes"]).replace("|", "/")[:180]
        lines.append(f"| {row['ID']} | {row['File']} | {row['Score']} | {row['Retrieval']} | {row['Citation']} | {row['Hallucination']} | {notes} |")
    if len(failed) > 80:
        lines.append(f"| ... | ... | ... | ... | ... | ... | Con {len(failed) - 80} case trong CSV |")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-module", default="/tmp/run_300_audit_container.py")
    parser.add_argument("--postfix-module", default="/tmp/run_postfix_rerun_container.py")
    parser.add_argument("--raw-results", default="/tmp/rag_audit_300/manual_test_results_raw.json")
    parser.add_argument("--username", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    audit = load_module("audit300", args.audit_module)
    postfix = load_module("postfix", args.postfix_module)
    container = audit.build_container(audit.get_settings())
    profiles = audit.build_profiles(container, args.username, args.chat_id)
    profile_by_name = {profile.original_name: profile for profile in profiles}

    base_cases = [clone_case(case, "B300", "Base 300") for case in audit.build_cases(profiles)]
    focused_cases = build_focused_cases(audit, Path(args.raw_results), profile_by_name, 65)
    extra_40 = build_extra_40(postfix, audit, profiles)
    extra_45 = build_extra_45(audit, profiles)
    all_cases = [*base_cases, *focused_cases, *extra_40, *extra_45]
    if len(all_cases) != 450:
        raise RuntimeError(f"Expected 450 cases, got {len(all_cases)}")

    print(f"profiles={len(profiles)} cases={len(all_cases)}", flush=True)
    checkpoint_path = out_dir / "checkpoint.json"
    rows: list[dict[str, Any]] = []
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        rows = list(checkpoint.get("rows") or [])
        print(f"resume={len(rows)}", flush=True)

    for index, case in enumerate(all_cases[len(rows):], start=len(rows) + 1):
        row = run_case(audit, container, args.username, args.chat_id, case)
        rows.append(row)
        if index % 5 == 0:
            checkpoint_path.write_text(json.dumps({"completed": index, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{index:03d}/450 {row['ID']} score={row['Score']} retrieval={row['Retrieval']} citation={row['Citation']} hall={row['Hallucination']} latency_ms={row['LatencyMs']}", flush=True)

    summary = summarize(rows, len(profiles))
    failed_rows = [
        row for row in rows
        if float(row["Score"]) < 1.0 or not is_yes(row["Retrieval"]) or not is_yes(row["Citation"]) or str(row["Hallucination"]).startswith("C")
    ]
    write_csv(out_dir / "unified_450_results.csv", rows)
    write_csv(out_dir / "unified_450_failed_cases.csv", failed_rows)
    (out_dir / "unified_450_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(out_dir / "unified_450_report.md", summary, rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
