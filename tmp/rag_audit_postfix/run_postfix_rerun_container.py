from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from typing import Any


def load_audit_module(path: str):
    spec = importlib.util.spec_from_file_location("audit300", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load audit module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def score_value(item: dict[str, Any]) -> float:
    try:
        return float(item.get("evaluation", {}).get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def build_current_case(old_case: dict[str, Any], profile_by_name: dict[str, Any]) -> dict[str, Any] | None:
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
        if not text:
            continue
        terms.append(text)
        if len(terms) >= limit:
            break
    return terms


def build_extra_cases(audit: Any, profiles: list[Any]) -> list[dict[str, Any]]:
    profile_by_name = {profile.original_name: profile for profile in profiles}
    extras: list[dict[str, Any]] = []

    def add(case: dict[str, Any]) -> None:
        case = dict(case)
        case["id"] = f"EXT-{len(extras) + 1:03d}"
        case["group"] = "Postfix Extra"
        extras.append(case)

    # Excel row/sheet cases: these directly exercise structured_rows and sheet citation.
    for profile in [p for p in profiles if p.file_type in {"XLSX", "XLS"}][:4]:
        rows = audit.structured_rows_from_profile(profile)
        if rows:
            for sheet, row_number, values in rows[:2]:
                if row_number <= 0:
                    continue
                items = [(str(k), str(v)) for k, v in values.items() if str(v).strip()]
                expected = "; ".join(f"{key}: {value}" for key, value in items[:6])
                add(
                    audit.make_case(
                        "EXT-000",
                        "Postfix Extra",
                        [profile],
                        f'Trong file "{profile.original_name}", ở sheet "{sheet}", dòng {row_number} có thông tin gì?',
                        expected,
                        row_expected_terms(values),
                    )
                )

        sheets: list[str] = []
        for doc in profile.chunks:
            sheet_name = str(doc.metadata.get("sheet_name") or "").strip()
            if sheet_name and sheet_name not in sheets:
                sheets.append(sheet_name)
        if sheets:
            add(
                audit.make_case(
                    "EXT-000",
                    "Postfix Extra",
                    [profile],
                    f'Workbook "{profile.original_name}" có bao nhiêu sheet và tên gì?',
                    f"{len(sheets)} sheet: {', '.join(sheets)}",
                    [str(len(sheets)), *sheets[:5]],
                )
            )

    # Slide-specific cases: citation must stay on the requested slide.
    for profile in [p for p in profiles if p.file_type == "PPTX"][:5]:
        seen_slides: set[int] = set()
        for doc in profile.chunks:
            try:
                slide_number = int(doc.metadata.get("slide_number") or doc.metadata.get("slide") or 0)
            except (TypeError, ValueError):
                continue
            if slide_number <= 0 or slide_number in seen_slides:
                continue
            seen_slides.add(slide_number)
            terms = audit.extract_keywords(doc.page_content, limit=6) or profile.terms[:6]
            expected = "; ".join(audit.useful_lines(doc.page_content, max_lines=3)) or profile.title
            add(
                audit.make_case(
                    "EXT-000",
                    "Postfix Extra",
                    [profile],
                    f'Slide {slide_number} của file "{profile.original_name}" nói về nội dung gì?',
                    expected,
                    terms,
                )
            )
            if len(seen_slides) >= 2:
                break

    # OCR/vision smoke cases.
    for profile in [p for p in profiles if p.file_type in {"PNG", "JPG", "JPEG"}][:6]:
        terms = profile.terms[:6] or audit.extract_keywords(profile.text, limit=6)
        add(
            audit.make_case(
                "EXT-000",
                "Postfix Extra",
                [profile],
                f'Trong ảnh "{profile.original_name}", nội dung chữ chính là gì?',
                profile.title,
                terms,
            )
        )

    # Negative/fallback cases: must not invent missing information.
    negative_pairs = [
        ("AI Document Question Answering System.pptx", "blockchain"),
        ("bai_trinh_chieu_mau_thu_vien_thong_minh.pptx", "mat khau admin"),
        ("bao_cao_quan_ly_rac_thai_nhua.pdf", "gia co phieu Apple"),
        ("ke_hoach_mau_du_lich_da_lat.md", "so tai khoan ngan hang"),
        ("infographic_mau_an_toan_mang.png", "hop dong lao dong"),
        ("pdf_01_nang_luong_mat_troi.pdf", "thong tin bao hiem"),
    ]
    for file_name, topic in negative_pairs:
        profile = profile_by_name.get(file_name)
        if profile is None:
            continue
        add(
            audit.make_case(
                "EXT-000",
                "Postfix Extra",
                [profile],
                f'Trong file "{file_name}" có thông tin về {topic} không?',
                "Không tìm thấy thông tin trong tài liệu.",
                ["không", "không tìm thấy", "không có thông tin"],
                kind="negative",
                forbidden_terms=[topic],
            )
        )

    # Cross-document comparison and ambiguous summary cases.
    comparison_names = [
        ("bao_cao_mau_chuyen_doi_so_giao_duc.pdf", "docx_01_thu_vien_so.docx"),
        ("pdf_01_nang_luong_mat_troi.pdf", "poster_mau_nang_luong_tai_tao.jpg"),
        ("md_02_app_chi_tieu.md", "xlsx_01_bao_cao_doanh_thu.xlsx"),
    ]
    for left_name, right_name in comparison_names:
        left = profile_by_name.get(left_name)
        right = profile_by_name.get(right_name)
        if left is None or right is None:
            continue
        add(
            audit.make_case(
                "EXT-000",
                "Postfix Extra",
                [left, right],
                f'So sánh nội dung của "{left_name}" và "{right_name}".',
                f"Cần nhắc đến cả hai file: {left.title}; {right.title}",
                (left.terms[:3] + right.terms[:3])[:8],
            )
        )

    for file_name in ["Test pdf.pdf", "Test docx.docx", "content_summary.md"]:
        profile = profile_by_name.get(file_name)
        if profile is None:
            continue
        add(
            audit.make_case(
                "EXT-000",
                "Postfix Extra",
                [profile],
                f'Tóm tắt ngắn nội dung chính của "{file_name}" trong 3 ý.',
                profile.title,
                profile.terms[:6],
            )
        )

    return extras


def run_case(audit: Any, container: Any, username: str, chat_id: str, case: dict[str, Any]) -> dict[str, Any]:
    latency, answer, sources = audit.ask_case(container, username, chat_id, case)
    evaluation = audit.evaluate_case(case, answer, sources)
    evaluation["latency_ms"] = round(latency * 1000, 2)
    return {
        "ID": case["id"],
        "File": ", ".join(case["files"]),
        "Loai file": case["file_type"],
        "Nhom": case["group"],
        "Cau hoi": case["question"],
        "Dap an chuan": case["expected_answer"],
        "Cau tra loi he thong": evaluation["actual_answer"],
        "Nguon/Citation": evaluation["sources"],
        "Retrieval": evaluation["retrieval"],
        "Citation": evaluation["citation"],
        "Answer": evaluation["answer_status"],
        "Diem": evaluation["score"],
        "Hallucination": evaluation["hallucination"],
        "Muc do loi": evaluation["severity"],
        "Ghi chu": evaluation["notes"],
        "De xuat fix": evaluation["fix"],
        "Latency ms": evaluation["latency_ms"],
    }


def summarize(rows: list[dict[str, Any]], *, prefix: str = "") -> OrderedDict[str, Any]:
    total = len(rows)
    full = sum(1 for row in rows if float(row["Diem"]) == 1.0)
    partial = sum(1 for row in rows if float(row["Diem"]) == 0.5)
    fail = sum(1 for row in rows if float(row["Diem"]) == 0.0)
    retrieval = sum(1 for row in rows if row["Retrieval"] == "Đúng")
    citation = sum(1 for row in rows if row["Citation"] == "Đúng")
    hallucination = sum(1 for row in rows if row["Hallucination"] == "Có")
    latencies = [float(row["Latency ms"]) for row in rows if row["Latency ms"] not in {"", None}]
    return OrderedDict(
        [
            (f"{prefix}Total", total),
            (f"{prefix}Full Correct", full),
            (f"{prefix}Partial", partial),
            (f"{prefix}Fail", fail),
            (f"{prefix}Answer Accuracy", f"{full}/{total} = {audit_percent(full / max(1, total))}"),
            (f"{prefix}Retrieval Correctness", f"{retrieval}/{total} = {audit_percent(retrieval / max(1, total))}"),
            (f"{prefix}Citation Correctness", f"{citation}/{total} = {audit_percent(citation / max(1, total))}"),
            (f"{prefix}Hallucination", hallucination),
            (f"{prefix}Mean Latency", f"{statistics.mean(latencies):.2f} ms" if latencies else "N/A"),
        ]
    )


def audit_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_simple_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    import csv

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(
    path: Path,
    *,
    subset_rows: list[dict[str, Any]],
    extra_rows: list[dict[str, Any]],
    baseline_counter: Counter,
) -> None:
    all_rows = [*subset_rows, *extra_rows]
    summary = summarize(all_rows)
    subset_summary = summarize(subset_rows, prefix="Rerun Failed/Focused ")
    extra_summary = summarize(extra_rows, prefix="Extra ")

    lines = [
        "# Post-fix Rerun Report",
        "",
        "## Tong quan",
    ]
    for key, value in summary.items():
        lines.append(f"- **{key}:** {value}")
    lines.extend(
        [
            "",
            "## So sanh subset truoc/sau",
            f"- **Baseline subset full/partial/fail:** {baseline_counter.get(1.0, 0)} / {baseline_counter.get(0.5, 0)} / {baseline_counter.get(0.0, 0)}",
        ]
    )
    for key, value in subset_summary.items():
        lines.append(f"- **{key}:** {value}")
    lines.append("")
    lines.append("## Cau hoi bo sung")
    for key, value in extra_summary.items():
        lines.append(f"- **{key}:** {value}")

    failed = [row for row in all_rows if float(row["Diem"]) < 1.0 or row["Retrieval"] != "Đúng" or row["Citation"] != "Đúng" or row["Hallucination"] == "Có"]
    lines.extend(
        [
            "",
            "## Cac case con can xem lai",
            "| ID | File | Nhom | Diem | Retrieval | Citation | Hallucination | Ghi chu |",
            "|---|---|---|---:|---|---|---|---|",
        ]
    )
    for row in failed[:80]:
        note = str(row["Ghi chu"]).replace("|", "/")[:180]
        lines.append(
            f"| {row['ID']} | {row['File']} | {row['Nhom']} | {row['Diem']} | {row['Retrieval']} | {row['Citation']} | {row['Hallucination']} | {note} |"
        )
    if len(failed) > 80:
        lines.append(f"| ... | ... | ... | ... | ... | ... | ... | Con {len(failed) - 80} case trong CSV/XLSX |")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-module", required=True)
    parser.add_argument("--raw-results", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-focused", type=int, default=65)
    args = parser.parse_args()

    audit = load_audit_module(args.audit_module)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    container = audit.build_container(audit.get_settings())
    profiles = audit.build_profiles(container, args.username, args.chat_id)
    profile_by_name = {profile.original_name: profile for profile in profiles}

    raw_payload = json.loads(Path(args.raw_results).read_text(encoding="utf-8"))
    raw_results = list(raw_payload.get("results") or [])

    focused_candidates: list[tuple[tuple[int, int, float, str], dict[str, Any], float]] = []
    baseline_scores: Counter = Counter()
    seen_ids: set[str] = set()
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
    for item in raw_results:
        case = item.get("case") or {}
        group = str(case.get("group") or "")
        score = score_value(item)
        if score < 1.0 or group in {"Negative/Hallucination", "Table/Numeric", "Slide/Presentation"}:
            current_case = build_current_case(case, profile_by_name)
            if current_case is None:
                continue
            if current_case["id"] in seen_ids:
                continue
            seen_ids.add(current_case["id"])
            severity = str((item.get("evaluation") or {}).get("severity") or "None")
            priority = (
                group_order.get(group, 9),
                severity_order.get(severity, 9),
                score,
                str(current_case["id"]),
            )
            focused_candidates.append((priority, current_case, score))

    focused_candidates.sort(key=lambda item: item[0])
    max_focused = max(0, int(args.max_focused or 0))
    if max_focused:
        focused_candidates = focused_candidates[:max_focused]

    focused_cases = []
    for _, current_case, score in focused_candidates:
        baseline_scores[score] += 1
        focused_cases.append(current_case)

    extra_cases = build_extra_cases(audit, profiles)

    print(f"profiles={len(profiles)} focused_cases={len(focused_cases)} extra_cases={len(extra_cases)}", flush=True)

    focused_rows: list[dict[str, Any]] = []
    extra_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []

    for index, case in enumerate(focused_cases, start=1):
        row = run_case(audit, container, args.username, args.chat_id, case)
        focused_rows.append(row)
        raw_rows.append({"case": case, "row": row})
        print(f"focused {index}/{len(focused_cases)} score={row['Diem']} id={row['ID']}", flush=True)

    for index, case in enumerate(extra_cases, start=1):
        row = run_case(audit, container, args.username, args.chat_id, case)
        extra_rows.append(row)
        raw_rows.append({"case": case, "row": row})
        print(f"extra {index}/{len(extra_cases)} score={row['Diem']} id={row['ID']}", flush=True)

    all_rows = [*focused_rows, *extra_rows]
    failed_rows = [
        row for row in all_rows
        if float(row["Diem"]) < 1.0 or row["Retrieval"] != "Đúng" or row["Citation"] != "Đúng" or row["Hallucination"] == "Có"
    ]

    write_simple_csv(out_dir / "postfix_rerun_results.csv", all_rows)
    write_simple_csv(out_dir / "postfix_failed_cases.csv", failed_rows)
    write_markdown(out_dir / "postfix_rerun_report.md", subset_rows=focused_rows, extra_rows=extra_rows, baseline_counter=baseline_scores)

    summary = {
        "focused": summarize(focused_rows),
        "extra": summarize(extra_rows),
        "all": summarize(all_rows),
        "baseline_scores": dict(baseline_scores),
        "failed_count": len(failed_rows),
    }
    (out_dir / "postfix_rerun_raw.json").write_text(
        json.dumps({"summary": summary, "results": raw_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
