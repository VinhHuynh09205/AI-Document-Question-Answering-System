import json
import re
import time
import unicodedata
from pathlib import Path

from app.core.config import Settings
from app.core.container import build_container


OWNER = "__guest__-rqreal9d1bfed0f204417f9617"
CHAT_ID = "2c680870f54d4f528cf5949c3bf338f4"

CASES = [
    {
        "id": "RQ-DOCX-01",
        "file": "Test docx.docx",
        "question": "Đề tài nghiên cứu trong báo cáo là gì?",
        "anchors": [["đề tài"], ["Nghiên cứu, ứng dụng mô hình AI"], ["đồ thị tri thức"]],
    },
    {
        "id": "RQ-DOCX-02",
        "file": "Test docx.docx",
        "question": "Giảng viên hướng dẫn là ai?",
        "anchors": [["Giảng viên hướng dẫn"], ["Nguyễn Văn Huy"]],
    },
    {
        "id": "RQ-DOCX-03",
        "file": "Test docx.docx",
        "question": "Kiến trúc retrieval nổi bật được nêu là gì?",
        "anchors": [["Hybrid GraphRAG"], ["Qdrant"], ["Neo4j"]],
    },
    {
        "id": "RQ-DOCX-04",
        "file": "Test docx.docx",
        "question": "Sinh viên thực hiện là ai?",
        "anchors": [["Sinh viên thực hiện"], ["Huỳnh Bá Thành"]],
    },
    {
        "id": "RQ-DOCX-05",
        "file": "Test docx.docx",
        "question": "Chỉ số của kiến trúc Hybrid là bao nhiêu?",
        "anchors": [["Hit@5"], ["94.00", "94,00"], ["Recall", "0.9400"]],
    },
    {
        "id": "RQ-DOCX-06",
        "file": "Test docx.docx",
        "question": "Hạn chế vận hành nào được nêu trong báo cáo?",
        "anchors": [["Streaming"], ["Gemini"], ["chờ", "hoàn tất"]],
    },
    {
        "id": "RQ-XLSX-01",
        "file": "Test xlsx.xlsx",
        "question": "Workbook có bao nhiêu sheet và tên gì?",
        "anchors": [["Sheet1"], ["Sheet2"], ["Sheet4"]],
    },
    {
        "id": "RQ-XLSX-02",
        "file": "Test xlsx.xlsx",
        "question": "Ở Sheet1, thí sinh No.1 có tổng điểm và kết quả gì?",
        "anchors": [["No.", "No"], ["1"], ["34"], ["合格"]],
    },
    {
        "id": "RQ-XLSX-03",
        "file": "Test xlsx.xlsx",
        "question": "Ở Sheet1, ai có tổng điểm cao nhất trong các dòng mẫu?",
        "anchors": [["山下"], ["恵子"], ["36.5"], ["合格"]],
    },
    {
        "id": "RQ-IMG-OCR-01",
        "file": "Test JPG.jpg",
        "question": "Email liên hệ trong tài liệu OCR là gì?",
        "anchors": [["qa-team@example.com"]],
    },
    {
        "id": "RQ-IMG-OCR-02",
        "file": "Test JPG.jpg",
        "question": "Module nào có trạng thái Warning?",
        "anchors": [["Vector Index"], ["Warning"]],
    },
    {
        "id": "RQ-IMG-OCR-03",
        "file": "Test JPG.jpg",
        "question": "Workspace ghi trên tài liệu là gì?",
        "anchors": [["Demo-Test-01"]],
    },
    {
        "id": "RQ-MD-01",
        "file": "Test md.md",
        "question": "RAG là viết tắt của cụm từ nào?",
        "anchors": [["Retrieval-Augmented Generation"]],
    },
    {
        "id": "RQ-MD-02",
        "file": "Test md.md",
        "question": "Top-k Retrieval được mô tả ra sao?",
        "anchors": [["Top-k Retrieval"], ["k đoạn tài liệu", "5 chunk", "chunk liên quan"], ["tương đồng", "tuong dong"]],
    },
    {
        "id": "RQ-MD-03",
        "file": "Test md.md",
        "question": "Fallback dùng khi nào?",
        "anchors": [["fallback"], ["không tìm thấy context phù hợp", "không đủ liên quan"]],
    },
    {
        "id": "RQ-PDFT-01",
        "file": "Test pdf.pdf",
        "question": "Chương 1 của tài liệu PDF nói về nội dung gì?",
        "anchors": [["Chương 1", "Chuong 1"], ["thị giác máy tính", "thi giac may tinh"], ["xử lý ảnh", "xu ly anh"]],
    },
    {
        "id": "RQ-PDFT-02",
        "file": "Test pdf.pdf",
        "question": "Bài thực hành chương 1 yêu cầu cài thư viện gì?",
        "anchors": [["OpenCV"], ["Pillow"]],
    },
    {
        "id": "RQ-PDFT-03",
        "file": "Test pdf.pdf",
        "question": "Trang cuối tài liệu là mục gì?",
        "anchors": [["Q & A", "Q&A"]],
    },
    {
        "id": "RQ-PDFS-01",
        "file": "Test pdf scan.pdf",
        "question": "Trang 1 file scan hiển thị nhãn gì?",
        "anchors": [["Hình 1", "Hinh 1"], ["Tre", "Viet Nam", "TreViet"]],
    },
    {
        "id": "RQ-PDFS-02",
        "file": "Test pdf scan.pdf",
        "question": "File scan có bao nhiêu trang?",
        "anchors": [["total_pages", "total pages", "3"], ["page", "trang"]],
    },
    {
        "id": "RQ-PDFS-03",
        "file": "Test pdf scan.pdf",
        "question": "Có trích được thông tin liên hệ từ file scan này không?",
        "anchors": [["Hình 1", "Hinh 1", "Hình 2", "Hình 3"], ["pdf scan"]],
    },
    {
        "id": "RQ-PPTX-01",
        "file": "Test pptx.pptx",
        "question": "Tiêu đề slide đầu là gì?",
        "anchors": [["オフィス業務"]],
    },
    {
        "id": "RQ-PPTX-02",
        "file": "Test pptx.pptx",
        "question": "Bài giảng khuyến nghị làm việc tối thiểu bao lâu ở cùng công ty?",
        "anchors": [["最低3年間", "最低３年間"], ["同じ会社"]],
    },
    {
        "id": "RQ-PPTX-03",
        "file": "Test pptx.pptx",
        "question": "Thông điệp về khác biệt văn hóa là gì?",
        "anchors": [["文化"], ["習慣"], ["考え方"], ["違う"]],
    },
    {
        "id": "RQ-TXT-01",
        "file": "test txt.txt",
        "question": "Du lịch sinh thái là gì?",
        "anchors": [["Du lịch sinh thái"], ["thiên nhiên"], ["bảo vệ môi trường"]],
    },
    {
        "id": "RQ-TXT-02",
        "file": "test txt.txt",
        "question": "Cần Giờ có vai trò gì trong hệ sinh thái?",
        "anchors": [["Cần Giờ"], ["dự trữ sinh quyển"], ["hấp thụ carbon"]],
    },
    {
        "id": "RQ-TXT-03",
        "file": "test txt.txt",
        "question": "Nguyên tắc phát triển du lịch sinh thái bền vững gồm gì?",
        "anchors": [["giới hạn"], ["không phá vỡ môi trường sống", "bảo tồn"], ["vật liệu thân thiện"], ["giáo dục ý thức"]],
    },
    {
        "id": "RQ-IMGTXT-01",
        "file": "Test PNG.png",
        "question": "Quán mở cửa khung giờ nào?",
        "anchors": [["OPEN"], ["07:00"], ["22:00"]],
    },
    {
        "id": "RQ-IMGTXT-02",
        "file": "Test jpeg.jpeg",
        "question": "Tổng đơn hàng là bao nhiêu?",
        "anchors": [["Tổng đơn hàng"], ["260"]],
    },
    {
        "id": "RQ-IMGTXT-03",
        "file": "Test jpeg.jpeg",
        "question": "Tổng doanh thu là bao nhiêu?",
        "anchors": [["Tổng doanh thu"], ["78.7M", "78.7"]],
    },
]


def fold(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if unicodedata.category(ch) != "Mn"
    )
    text = text.replace("Đ", "D").replace("đ", "d").casefold()
    return re.sub(r"\s+", " ", text).strip()


def doc_text(doc) -> str:
    metadata = doc.metadata
    keep = {
        key: metadata.get(key)
        for key in [
            "document_name",
            "source",
            "page",
            "page_number",
            "total_pages",
            "slide_number",
            "slide_title",
            "sheet_name",
            "row_number",
            "row_index",
            "range_address",
            "content_type",
        ]
        if metadata.get(key) is not None
    }
    return f"{doc.page_content or ''}\nMETADATA: {json.dumps(keep, ensure_ascii=False)}"


def group_hit(text: str, group: list[str]) -> bool:
    folded_text = fold(text)
    return any(fold(anchor) in folded_text for anchor in group)


def is_relevant(doc, case: dict) -> bool:
    text = doc_text(doc)
    return all(group_hit(text, group) for group in case["anchors"])


def short_ref(doc) -> str:
    metadata = doc.metadata
    name = metadata.get("document_name") or Path(str(metadata.get("source", ""))).name
    locations: list[str] = []
    if metadata.get("page") or metadata.get("page_number"):
        locations.append(f"trang {metadata.get('page') or metadata.get('page_number')}")
    if metadata.get("slide_number"):
        locations.append(f"slide {metadata.get('slide_number')}")
    if metadata.get("sheet_name"):
        locations.append(f"sheet {metadata.get('sheet_name')}")
    if metadata.get("row_number") or metadata.get("row_index"):
        locations.append(f"row {metadata.get('row_number') or metadata.get('row_index')}")
    return f"{name}" + (f" ({', '.join(locations[:3])})" if locations else "")


def main() -> None:
    settings = Settings()
    container = build_container(settings)
    service = container.question_answering_service

    store_payload = json.loads(Path(settings.vector_store_path, "documents.json").read_text(encoding="utf-8"))
    source_by_name: dict[str, str] = {}
    for item in store_payload:
        metadata = item.get("metadata", {})
        if metadata.get("owner") != OWNER or metadata.get("chat_id") != CHAT_ID:
            continue
        name = metadata.get("document_name") or Path(str(metadata.get("source", ""))).name.split("_", 1)[-1]
        source_by_name.setdefault(name, metadata.get("source"))

    missing_sources = [case["file"] for case in CASES if case["file"] not in source_by_name]
    if missing_sources:
        raise RuntimeError(f"Missing sources: {missing_sources}")

    results: list[dict] = []
    for index, case in enumerate(CASES, start=1):
        question = case["question"]
        raw_question = service._normalize_text_query(question)
        normalized_question = service._normalize_question(raw_question)
        metadata_filter = {
            "owner": OWNER,
            "chat_id": CHAT_ID,
            "source": source_by_name[case["file"]],
        }
        route = service._query_router.route(raw_question, metadata_filter)

        started_at = time.perf_counter()
        docs = service._retrieve_context_docs(
            raw_question=raw_question,
            normalized_question=normalized_question,
            metadata_filter=route.metadata_filter,
            top_k=5,
        )
        docs = [doc for doc in docs if doc.page_content.strip()]
        docs = service._merge_scoped_context_docs(
            raw_question=raw_question,
            normalized_question=normalized_question,
            metadata_filter=route.metadata_filter,
            context_docs=docs,
            top_k=5,
        )
        latency_ms = (time.perf_counter() - started_at) * 1000

        top5 = docs[:5]
        rank = 0
        for candidate_rank, doc in enumerate(top5, start=1):
            if is_relevant(doc, case):
                rank = candidate_rank
                break

        reciprocal_rank = (1 / rank) if rank else 0.0
        result = {
            "id": case["id"],
            "file": case["file"],
            "question": question,
            "rank": rank,
            "hit5": 1 if rank else 0,
            "rr": reciprocal_rank,
            "status": "Pass" if rank else "Fail",
            "latency_ms": round(latency_ms, 2),
            "matched_ref": short_ref(top5[rank - 1]) if rank else "",
            "top5": [short_ref(doc) for doc in top5],
        }
        results.append(result)
        print(
            f"{index:02d}/{len(CASES)} {case['id']} "
            f"rank={rank} rr={reciprocal_rank:.4f} {result['matched_ref']}"
        )

    total = len(results)
    hit5_count = sum(item["hit5"] for item in results)
    summary = {
        "scope": "file-scoped hybrid retrieval on current FAISS index",
        "owner": OWNER,
        "chat_id": CHAT_ID,
        "total": total,
        "hit5_count": hit5_count,
        "hit5": hit5_count / total if total else 0.0,
        "mrr": sum(item["rr"] for item in results) / total if total else 0.0,
        "mean_latency_ms": sum(item["latency_ms"] for item in results) / total if total else 0.0,
        "results": results,
    }
    output_path = Path("tmp/hit5_mrr_current.json")
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "SUMMARY "
        + json.dumps(
            {
                key: summary[key]
                for key in ["total", "hit5_count", "hit5", "mrr", "mean_latency_ms"]
            },
            ensure_ascii=False,
        )
    )
    print(f"WROTE {output_path}")


if __name__ == "__main__":
    main()
