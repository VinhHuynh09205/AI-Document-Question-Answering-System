import importlib.util
from pathlib import Path


BASE_EVAL_PATH = Path("tmp/evaluate_hit5_mrr.py")
spec = importlib.util.spec_from_file_location("hit5_mrr_base", BASE_EVAL_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load {BASE_EVAL_PATH}")

base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


EXTRA_CASES = [
    {
        "id": "RQ-PPTX2-01",
        "file": "AI Document Question Answering System.pptx",
        "question": "Đề tài ở slide đầu là gì?",
        "anchors": [["ĐỀ TÀI", "Đề tài"], ["AI Document Question Answering System"]],
    },
    {
        "id": "RQ-PPTX2-02",
        "file": "AI Document Question Answering System.pptx",
        "question": "Kiến trúc tổng thể của hệ thống có backend và data layer nào?",
        "anchors": [["Backend FastAPI"], ["PostgreSQL"], ["FAISS"]],
    },
    {
        "id": "RQ-PPTX2-03",
        "file": "AI Document Question Answering System.pptx",
        "question": "Pipeline xử lý tài liệu dùng chunk_size và overlap bao nhiêu?",
        "anchors": [["chunk_size"], ["1000"], ["overlap"], ["150"]],
    },
    {
        "id": "RQ-XLSX2-01",
        "file": "file_excel_mau_song_xanh.xlsx",
        "question": "Workbook sống xanh có những sheet nào?",
        "anchors": [["Du_lieu_chien_dich"], ["Tong_quan"]],
    },
    {
        "id": "RQ-XLSX2-02",
        "file": "file_excel_mau_song_xanh.xlsx",
        "question": "Tổng lượt tham gia trong sheet tổng quan là bao nhiêu?",
        "anchors": [["Tổng lượt tham gia"], ["1586"]],
    },
    {
        "id": "RQ-XLSX2-03",
        "file": "file_excel_mau_song_xanh.xlsx",
        "question": "Ở sheet tổng quan, khu vực Căn tin có bao nhiêu người tham gia và rác tái chế?",
        "anchors": [["Căn tin"], ["487"], ["129.6"]],
    },
    {
        "id": "RQ-XLSX2-04",
        "file": "file_excel_mau_song_xanh.xlsx",
        "question": "Ngày 2026-05-03 có hoạt động gì và ai phụ trách?",
        "anchors": [["2026-05-03"], ["Workshop sống xanh"], ["Huy"]],
    },
    {
        "id": "RQ-DOCX2-01",
        "file": "bao_cao_an_toan_du_lieu_ca_nhan.docx",
        "question": "Báo cáo DOCX nói về vấn đề gì?",
        "anchors": [["AN TOÀN DỮ LIỆU CÁ NHÂN"], ["bảo vệ dữ liệu cá nhân"], ["ứng dụng trực tuyến"]],
    },
    {
        "id": "RQ-DOCX2-02",
        "file": "bao_cao_an_toan_du_lieu_ca_nhan.docx",
        "question": "Nguyên nhân chính gây rủi ro dữ liệu cá nhân là gì?",
        "anchors": [["mật khẩu yếu"], ["thiếu mã hóa"], ["không đúng quyền"], ["xóa hoặc ẩn danh"]],
    },
    {
        "id": "RQ-DOCX2-03",
        "file": "bao_cao_an_toan_du_lieu_ca_nhan.docx",
        "question": "Bảng đề xuất biện pháp gồm các nhóm giải pháp nào?",
        "anchors": [["Xác thực mạnh"], ["Mã hóa dữ liệu"], ["Phân quyền"], ["Nhật ký hệ thống"]],
    },
    {
        "id": "RQ-PDF2-01",
        "file": "bao_cao_quan_ly_rac_thai_nhua.pdf",
        "question": "Báo cáo PDF nói về vấn đề gì?",
        "anchors": [["QUẢN LÝ RÁC THẢI NHỰA"], ["KHU DÂN CƯ"]],
    },
    {
        "id": "RQ-PDF2-02",
        "file": "bao_cao_quan_ly_rac_thai_nhua.pdf",
        "question": "Vi nhựa gây hậu quả gì?",
        "anchors": [["vi nhựa"], ["nguồn nước"], ["chuỗi thức ăn"], ["sức khỏe"]],
    },
    {
        "id": "RQ-PDF2-03",
        "file": "bao_cao_quan_ly_rac_thai_nhua.pdf",
        "question": "Kế hoạch hành động đề xuất gồm những hoạt động nào?",
        "anchors": [["Phân loại tại nguồn"], ["Ngày đổi rác lấy quà"], ["Giảm nhựa dùng một"], ["Theo dõi số liệu"]],
    },
]


base.CASES = [*base.CASES, *EXTRA_CASES]


if __name__ == "__main__":
    base.main()
