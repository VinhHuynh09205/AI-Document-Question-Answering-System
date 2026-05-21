from __future__ import annotations

import csv
import json
import pathlib
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict

import jwt
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


BASE = "http://127.0.0.1:8000/api/v1"
SECRET = "change-me-in-production"
CONTEXT_PATH = pathlib.Path("tmp/rag_audit/manual_upload_context.json")
OUT_DIR = pathlib.Path("tmp/rag_audit")


def fold(value: object) -> str:
    text = str(value or "").replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).lower().strip()


def is_fallback(answer: str) -> bool:
    folded = fold(answer)
    return any(
        phrase in folded
        for phrase in [
            "khong tim thay",
            "khong co thong tin",
            "khong du thong tin",
            "khong the trich",
            "khong nam trong tai lieu",
            "khong de cap",
        ]
    )


def has_any(answer: str, terms: list[str]) -> bool:
    folded = fold(answer)
    return any(fold(term) in folded for term in terms)


def has_all(answer: str, terms: list[str]) -> bool:
    folded = fold(answer)
    return all(fold(term) in folded for term in terms)


def source_matches(sources: list[str], expected_files: list[str], answer: str) -> bool:
    if is_fallback(answer):
        return True
    if not expected_files:
        return True
    folded_sources = fold("\n".join(str(source) for source in sources))
    return all(fold(name) in folded_sources for name in expected_files)


def compact_answer(answer: str, limit: int = 900) -> str:
    compact = re.sub(r"\s+", " ", str(answer or "")).strip()
    return compact[:limit]


class AuditRunner:
    def __init__(self) -> None:
        self.ctx = json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
        self.username = self.ctx["username"]
        self.chat_id = self.ctx["chat_id"]
        self.docs = {doc["original_name"]: doc for doc in self.ctx["documents"]}
        self.cases: list[dict[str, object]] = []

    def doc_id(self, filename: str) -> str:
        return self.docs[filename]["document_id"]

    def add(
        self,
        test_id: str,
        group: str,
        filename: str,
        file_type: str,
        question: str,
        expected: str,
        terms: list[str] | None = None,
        *,
        all_terms: bool = False,
        fallback: bool = False,
        selected: list[str] | None = None,
        sources: list[str] | None = None,
        forbidden: list[str] | None = None,
        expect_type: str | None = None,
    ) -> None:
        if selected is None:
            selected = [self.doc_id(filename)] if filename in self.docs else None
        self.cases.append(
            {
                "id": test_id,
                "group": group,
                "file": filename,
                "type": file_type,
                "question": question,
                "expected": expected,
                "terms": terms or [],
                "expect_type": expect_type
                or ("fallback" if fallback else "contains_all" if all_terms else "contains_any"),
                "selected": selected,
                "sources": sources if sources is not None else ([filename] if filename in self.docs else []),
                "forbidden": forbidden or [],
            }
        )

    def build_cases(self) -> None:
        self.add("A01", "A-Direct", "AI Document Question Answering System.pptx", "PPTX", "De tai trong slide dau la gi?", "AI Document Question Answering System", ["AI Document Question Answering System"])
        self.add("B01", "B-Detail", "AI Document Question Answering System.pptx", "PPTX", "Giang vien huong dan trong PPTX la ai?", "Nguyen Van Huy", ["Nguyen Van Huy"])
        self.add("A02", "A-Direct", "bai_trinh_chieu_mau_thu_vien_thong_minh.pptx", "PPTX", "Bai trinh chieu mau noi ve chu de gi?", "Thu vien thong minh cho truong hoc hien dai", ["thu vien thong minh", "truong hoc hien dai"])
        self.add("B02", "B-Detail", "bai_trinh_chieu_mau_thu_vien_thong_minh.pptx", "PPTX", "Slide 1 co cac nhan chuc nang nao?", "Du lieu sach, Tim kiem nhanh, Goi y hoc tap", ["du lieu sach", "tim kiem nhanh", "goi y hoc tap"])
        self.add("A03", "A-Direct", "bao_cao_an_toan_du_lieu_ca_nhan.docx", "DOCX", "Tai lieu DOCX nay noi ve van de gi?", "An toan du lieu ca nhan trong ung dung so", ["an toan du lieu ca nhan", "ung dung so"])
        self.add("B03", "B-Detail", "bao_cao_an_toan_du_lieu_ca_nhan.docx", "DOCX", "Cac nguyen nhan thuong gap gay rui ro du lieu la gi?", "Mat khau yeu, thieu ma hoa, truy cap sai quyen, thieu quy trinh xoa/an danh", ["mat khau yeu", "ma hoa", "truy cap", "an danh"])
        self.add("A04", "A-Direct", "bao_cao_mau_chuyen_doi_so_giao_duc.pdf", "PDF", "PDF chuyen doi so giao duc noi ve noi dung gi?", "Chuyen doi so trong giao duc", ["chuyen doi so", "giao duc"])
        self.add("B04", "B-Detail", "bao_cao_mau_chuyen_doi_so_giao_duc.pdf", "PDF", "Muc tieu dau tien khi trien khai chuyen doi so giao duc la gi?", "Tang hieu qua quan ly", ["tang hieu qua quan ly"])
        self.add("A05", "A-Direct", "bao_cao_quan_ly_rac_thai_nhua.pdf", "PDF", "Bao cao rac thai nhua noi ve van de gi?", "Quan ly rac thai nhua tai khu dan cu", ["rac thai nhua", "khu dan cu"])
        self.add("B05", "B-Detail", "bao_cao_quan_ly_rac_thai_nhua.pdf", "PDF", "Ke hoach hanh dong de xuat gom nhung hoat dong nao?", "Phan loai tai nguon, ngay doi rac lay qua, giam nhua dung mot lan, theo doi so lieu", ["phan loai tai nguon", "doi rac lay qua", "giam nhua", "theo doi so lieu"])
        self.add("A06", "A-Direct", "content_summary.md", "MD", "File content_summary.md mo ta noi dung gi?", "Tong hop/ket qua trich xuat noi dung tai lieu test", ["total paragraphs", "dimensions", "tong"])
        self.add("B06", "B-Detail", "content_summary.md", "MD", "content_summary.md ghi tong so paragraph la bao nhieu?", "346", ["346"])
        self.add("E01", "E-Format", "file_excel_mau_song_xanh.xlsx", "XLSX", "File Excel song xanh co nhung sheet nao?", "Du_lieu_chien_dich va Tong_quan", ["Du_lieu_chien_dich", "Tong_quan"], all_terms=True)
        self.add("B07", "B-Detail", "file_excel_mau_song_xanh.xlsx", "XLSX", "Ngay 2026-05-01 co hoat dong gi va o khu vuc nao?", "Doi rac lay cay tai Ky tuc xa", ["doi rac lay cay", "ky tuc xa"], all_terms=True)
        self.add("A07", "A-Direct", "infographic_mau_an_toan_mang.png", "PNG", "Infographic PNG noi ve chu de gi?", "An toan mang cho sinh vien", ["an toan mang", "sinh vien"])
        self.add("B08", "B-Detail", "infographic_mau_an_toan_mang.png", "PNG", "Infographic neu nhung bien phap an toan mang nao?", "Mat khau manh, xac thuc hai lop, canh giac lien ket la, sao luu du lieu", ["mat khau", "xac thuc hai lop", "lien ket", "sao luu"])
        self.add("A08", "A-Direct", "ke_hoach_mau_du_lich_da_lat.md", "MD", "Ke hoach Markdown nay noi ve chuyen di nao?", "Du lich Da Lat", ["Da Lat", "chuyen di"])
        self.add("B09", "B-Detail", "ke_hoach_mau_du_lich_da_lat.md", "MD", "Nhom gia dinh gom bao nhieu nguoi va di chuyen bang gi?", "4 nguoi, xe khach tu TP.HCM", ["4", "xe khach"])
        self.add("A09", "A-Direct", "nhat_ky_mau_vuon_rau_do_thi.txt", "TXT", "Nhat ky TXT noi ve du an gi?", "Vuon rau do thi tren san thuong", ["vuon rau do thi", "san thuong"])
        self.add("B10", "B-Detail", "nhat_ky_mau_vuon_rau_do_thi.txt", "TXT", "Dien tich san thuong ban dau khoang bao nhieu?", "Khoang 30 met vuong", ["30", "met vuong"])
        self.add("A10", "A-Direct", "noi_dung_mau_thanh_pho_xanh.pdf", "PDF", "PDF Thanh pho Xanh 2030 huong den muc tieu gi?", "Giam rac thai nhua, tang khong gian xanh, di chuyen sach", ["giam rac thai nhua", "khong gian xanh", "di chuyen sach"])
        self.add("B11", "B-Detail", "noi_dung_mau_thanh_pho_xanh.pdf", "PDF", "Bang so lieu mau trong PDF Thanh pho Xanh co nhung chi so nao?", "Cay xanh moi 1.250, rac tai che 8,4 tan, nguoi tham gia 3.600, tuyen xe dap 12", ["1.250", "8,4", "3.600", "12"])
        self.add("A11", "A-Direct", "pdf_page_index.md", "MD", "pdf_page_index.md dung de lam gi?", "Chi muc/trich xuat theo trang cho PDF thi giac may tinh", ["tong quan ve thi giac may tinh", "total chars"])
        self.add("B12", "B-Detail", "pdf_page_index.md", "MD", "Trang dau trong pdf_page_index.md nhac toi noi dung gi?", "Tong quan ve thi giac may tinh va xu ly anh", ["tong quan ve thi giac may tinh", "xu ly anh"])
        self.add("A12", "A-Direct", "poster_mau_nang_luong_tai_tao.jpg", "JPG", "Poster JPG noi ve chu de gi?", "Nang luong tai tao trong doi song", ["nang luong tai tao", "doi song"])
        self.add("B13", "B-Detail", "poster_mau_nang_luong_tai_tao.jpg", "JPG", "Poster neu nhung loai nang luong nao?", "Dien mat troi, dien gio, sinh khoi va tiet kiem nang luong", ["dien mat troi", "dien gio", "sinh khoi"])
        self.add("A13", "A-Direct", "RETRIEVAL_TESTING_QUESTION_SET.md", "MD", "Bo test retrieval nay duoc xay dung de kiem tra gi?", "Retrieval theo nguon/noi dung/da ngon ngu/fallback", ["retrieval", "fallback", "da ngon ngu"])
        self.add("B14", "B-Detail", "RETRIEVAL_TESTING_QUESTION_SET.md", "MD", "Bo test nay liet ke nhung file anh nao?", "Test JPG.jpg, Test PNG.png, Test jpeg.jpeg", ["Test JPG.jpg", "Test PNG.png", "Test jpeg.jpeg"])
        self.add("A14", "A-Direct", "storyboard_mau_suc_khoe_hoc_duong.jpeg", "JPEG", "Storyboard JPEG noi ve chu de gi?", "Suc khoe hoc duong", ["suc khoe hoc duong"])
        self.add("B15", "B-Detail", "storyboard_mau_suc_khoe_hoc_duong.jpeg", "JPEG", "Storyboard mo ta bao nhieu canh?", "6 canh", ["6 canh", "canh 6"])
        self.add("A15", "A-Direct", "Test docx.docx", "DOCX", "De tai nghien cuu trong bao cao la gi?", "Nghien cuu, ung dung mo hinh AI, ket hop do thi tri thuc ho tro tra cuu luat CNTT", ["nghien cuu", "mo hinh ai", "do thi tri thuc"])
        self.add("B16", "B-Detail", "Test docx.docx", "DOCX", "Sinh vien thuc hien la ai?", "Huynh Ba Thanh", ["Huynh Ba Thanh"])
        self.add("A16", "A-Direct", "Test jpeg.jpeg", "JPEG", "Anh JPEG bao cao noi dung gi?", "Bao cao doanh thu thang 05/2026", ["doanh thu", "05/2026"])
        self.add("B17", "B-Detail", "Test jpeg.jpeg", "JPEG", "Tong don hang va tong doanh thu la bao nhieu?", "260 don hang, 78.7M", ["260", "78.7"])
        self.add("A17", "A-Direct", "Test JPG.jpg", "JPG", "Anh JPG OCR test co email lien he nao?", "qa-team@example.com", ["qa-team@example.com"])
        self.add("B18", "B-Detail", "Test JPG.jpg", "JPG", "Module nao co trang thai Warning?", "Vector Index", ["Vector Index", "Warning"])
        self.add("A18", "A-Direct", "Test md.md", "MD", "RAG la viet tat cua cum tu nao?", "Retrieval-Augmented Generation", ["Retrieval-Augmented Generation"])
        self.add("B19", "B-Detail", "Test md.md", "MD", "Fallback dung khi nao?", "Khi khong tim thay context phu hop de han che hallucination", ["khong tim thay context", "hallucination"])
        self.add("A19", "A-Direct", "Test pdf scan.pdf", "PDF_SCAN", "Trang 1 file scan hien thi nhan gi?", "Hinh 1: Tre Viet Nam", ["Hinh 1", "Tre"])
        self.add("B20", "B-Detail", "Test pdf scan.pdf", "PDF_SCAN", "File scan co bao nhieu trang?", "3 trang", ["3 trang", "3"])
        self.add("A20", "A-Direct", "Test pdf.pdf", "PDF", "Chuong 1 cua tai lieu PDF noi ve noi dung gi?", "Tong quan ve thi giac may tinh va xu ly anh", ["thi giac may tinh", "xu ly anh"])
        self.add("B21", "B-Detail", "Test pdf.pdf", "PDF", "Bai thuc hanh chuong 1 yeu cau cai thu vien gi?", "OpenCV va Pillow", ["OpenCV", "Pillow"], all_terms=True)
        self.add("A21", "A-Direct", "Test PNG.png", "PNG", "Quan mo cua khung gio nao?", "07:00 - 22:00", ["07:00", "22:00"], all_terms=True)
        self.add("B22", "B-Detail", "Test PNG.png", "PNG", "Wi-Fi cua quan la gi?", "MayCoffee_Free", ["MayCoffee_Free"])
        self.add("A22", "A-Direct", "Test pptx.pptx", "PPTX", "Tieu de slide dau la gi?", "\u30aa\u30d5\u30a3\u30b9\u696d\u52d9", ["\u30aa\u30d5\u30a3\u30b9\u696d\u52d9"])
        self.add("B23", "B-Detail", "Test pptx.pptx", "PPTX", "Bai giang khuyen nghi lam viec toi thieu bao lau o cung cong ty?", "3 nam / \u6700\u4f4e3\u5e74\u9593", ["3", "\u4f1a\u793e"])
        self.add("A23", "A-Direct", "test txt.txt", "TXT", "Du lich sinh thai la gi?", "Du lich gan voi thien nhien, van hoa dia phuong va bao ve moi truong", ["thien nhien", "van hoa dia phuong", "moi truong"])
        self.add("B24", "B-Detail", "test txt.txt", "TXT", "Can Gio co vai tro gi trong he sinh thai?", "Khu du tru sinh quyen, bao ve bo bien, hap thu carbon", ["bao ve bo bien", "carbon"])
        self.add("E02", "E-Format", "Test xlsx.xlsx", "XLSX", "Workbook Test xlsx co bao nhieu sheet va ten gi?", "3 sheet: Sheet4, Sheet2, Sheet1", ["3", "Sheet4", "Sheet2", "Sheet1"], all_terms=True)
        self.add("B25", "B-Detail", "Test xlsx.xlsx", "XLSX", "O Sheet1, thi sinh No.1 co tong diem va ket qua gi?", "34 va \u5408\u683c", ["34", "\u5408\u683c"], all_terms=True)

        self.add("C01", "C-Summary", "bao_cao_mau_chuyen_doi_so_giao_duc.pdf", "PDF", "Tom tat file PDF chuyen doi so giao duc trong 5 y ngan.", "Tom tat dung ve chuyen doi so giao duc", ["chuyen doi so", "giao duc"])
        self.add("C02", "C-Summary", "file_excel_mau_song_xanh.xlsx", "XLSX", "Tom tat file Excel song xanh nay noi ve du lieu gi.", "Chien dich song xanh trong truong hoc", ["chien dich song xanh", "truong hoc"])
        self.add("C03", "C-Summary", "storyboard_mau_suc_khoe_hoc_duong.jpeg", "JPEG", "Tom tat noi dung anh storyboard suc khoe hoc duong.", "6 canh ve suc khoe hoc duong", ["suc khoe hoc duong", "dinh duong", "van dong"])
        self.add("D01", "D-Cross", "noi_dung_mau_thanh_pho_xanh.pdf + bao_cao_quan_ly_rac_thai_nhua.pdf", "PDF", "So sanh PDF Thanh pho Xanh va PDF quan ly rac thai nhua khac nhau o diem nao?", "Mot file noi ve do thi xanh tong quat, mot file noi ve quan ly rac nhua khu dan cu", ["Thanh pho Xanh", "rac thai nhua"], selected=[self.doc_id("noi_dung_mau_thanh_pho_xanh.pdf"), self.doc_id("bao_cao_quan_ly_rac_thai_nhua.pdf")], sources=["noi_dung_mau_thanh_pho_xanh.pdf", "bao_cao_quan_ly_rac_thai_nhua.pdf"])
        self.add("D02", "D-Cross", "ke_hoach_mau_du_lich_da_lat.md + poster_mau_nang_luong_tai_tao.jpg", "MD+JPG", "Markdown du lich Da Lat va poster nang luong tai tao co cung chu de khong?", "Khong, mot file la du lich Da Lat, mot file la nang luong tai tao", ["Da Lat", "nang luong tai tao"], selected=[self.doc_id("ke_hoach_mau_du_lich_da_lat.md"), self.doc_id("poster_mau_nang_luong_tai_tao.jpg")], sources=["ke_hoach_mau_du_lich_da_lat.md", "poster_mau_nang_luong_tai_tao.jpg"])
        self.add("D03", "D-Cross", "infographic_mau_an_toan_mang.png + bao_cao_an_toan_du_lieu_ca_nhan.docx", "PNG+DOCX", "Anh an toan mang va DOCX an toan du lieu ca nhan giong nhau o diem nao?", "Deu lien quan bao ve thong tin/an toan so", ["an toan", "du lieu", "mat khau"], selected=[self.doc_id("infographic_mau_an_toan_mang.png"), self.doc_id("bao_cao_an_toan_du_lieu_ca_nhan.docx")], sources=["infographic_mau_an_toan_mang.png", "bao_cao_an_toan_du_lieu_ca_nhan.docx"])
        self.add("F01", "F-Negative", "ke_hoach_mau_du_lich_da_lat.md", "MD", "Tai lieu du lich Da Lat co noi ve blockchain khong?", "Khong tim thay blockchain trong tai lieu", fallback=True)
        self.add("F02", "F-Negative", "Test pdf scan.pdf", "PDF_SCAN", "Co trich duoc thong tin lien he tu file scan nay khong?", "Khong co email/so dien thoai ro rang", fallback=True)
        self.add("F03", "F-Negative", "file_excel_mau_song_xanh.xlsx", "XLSX", "Mat khau admin trong file Excel la gi?", "Khong tim thay trong tai lieu", fallback=True)
        self.add("F04", "F-Negative", "Test pptx.pptx", "PPTX", "Bai giang nay co email lien he nao?", "Khong tim thay email lien he", fallback=True)
        self.add("G01", "G-Ambiguous", "ALL", "MIXED", "Noi dung chinh la gi?", "He thong nen hoi ro tai lieu hoac tong hop khong bia", ["tai lieu", "file", "chon"], selected=None, sources=[], expect_type="clarify_or_answer")
        self.add("G02", "G-Ambiguous", "ALL", "MIXED", "Tom tat giup toi.", "He thong nen hoi ro pham vi hoac tom tat theo workspace, khong bia", ["tai lieu", "file", "chon", "tom tat"], selected=None, sources=[], expect_type="clarify_or_answer")
        self.add("H01", "H-Distractor", "poster_mau_nang_luong_tai_tao.jpg", "JPG", "Poster nang luong tai tao co noi ve du lich Da Lat dung khong?", "Khong, poster noi ve nang luong tai tao", ["khong", "nang luong tai tao"], forbidden=["lich trinh Da Lat"], expect_type="not_contains_and_fallback")
        self.add("H02", "H-Distractor", "bao_cao_quan_ly_rac_thai_nhua.pdf", "PDF", "Bao cao rac thai nhua co noi rang tong doanh thu la 78.7M dung khong?", "Khong, 78.7M thuoc anh doanh thu, khong nam trong bao cao rac thai nhua", ["khong", "rac thai nhua"], forbidden=["78.7M la tong doanh thu"], expect_type="not_contains_and_fallback")
        self.add("H03", "H-Distractor", "Test xlsx.xlsx", "XLSX", "Trong Test xlsx, thi sinh No.1 co tong doanh thu 78.7M phai khong?", "Khong, No.1 co tong diem 34 va ket qua hop le", ["khong", "34", "\u5408\u683c"], forbidden=["78.7M"], expect_type="not_contains_and_fallback")

    def token(self) -> str:
        return jwt.encode({"sub": self.username, "exp": int(time.time()) + 8 * 3600}, SECRET, algorithm="HS256")

    def ask(self, question: str, selected: list[str] | None) -> tuple[float, dict[str, object]]:
        payload: dict[str, object] = {"question": question}
        if selected is not None:
            payload["selected_document_ids"] = selected
        started = time.perf_counter()
        response = requests.post(
            f"{BASE}/workspace/chats/{self.chat_id}/ask",
            headers={"Authorization": f"Bearer {self.token()}"},
            json=payload,
            timeout=180,
        )
        latency = time.perf_counter() - started
        if response.status_code != 200:
            return latency, {"answer": f"HTTP {response.status_code}: {response.text[:500]}", "sources": []}
        return latency, response.json()

    def evaluate(self, case: dict[str, object], answer: str, sources: list[str]) -> dict[str, object]:
        expect_type = str(case["expect_type"])
        expected_terms = list(case.get("terms") or [])
        forbidden_terms = list(case.get("forbidden") or [])

        if expect_type == "fallback":
            ok = is_fallback(answer)
        elif expect_type == "contains_all":
            ok = has_all(answer, expected_terms)
        elif expect_type == "contains_any":
            ok = has_any(answer, expected_terms)
        elif expect_type == "clarify_or_answer":
            ok = has_any(answer, expected_terms) or has_any(answer, ["ban muon", "chon", "tai lieu nao", "file nao"])
        elif expect_type == "not_contains_and_fallback":
            forbidden_hit = has_any(answer, forbidden_terms)
            ok = (not forbidden_hit) and (is_fallback(answer) or has_any(answer, ["khong", "khong phai", "khac"]))
        else:
            ok = False

        src_ok = source_matches(sources, list(case.get("sources") or []), answer)
        hallucinated = False
        if expect_type == "fallback" and not is_fallback(answer):
            hallucinated = True
        if forbidden_terms and has_any(answer, forbidden_terms) and not has_any(answer, ["khong phai", "khong dung", "khac voi"]):
            hallucinated = True

        correctness = 5 if ok else 3 if expected_terms and has_any(answer, expected_terms[:1]) else 1 if not is_fallback(answer) else 0
        groundedness = 5 if src_ok and (ok or expect_type == "fallback") else 3 if src_ok else 1
        completeness = 5 if ok else 3 if correctness >= 3 else 1
        retrieval = 5 if src_ok else 3 if sources else 0
        fmt = 5
        if len(answer) > 1200 and not has_any(str(case["question"]), ["tom tat", "so sanh", "bang", "so do"]):
            fmt = 3
        if "```mermaid" in answer.lower() and not has_any(str(case["question"]), ["so do", "mindmap", "quy trinh", "truc quan"]):
            fmt = 2
        hallucination_score = 5 if ok and not hallucinated else 3 if not hallucinated else 1
        conclusion = "Pass" if ok and src_ok else "Fail"
        notes: list[str] = []
        if not ok:
            notes.append("Answer mismatch/fallback sai")
        if not src_ok:
            notes.append("Nguon/citation khong dung file ky vong")
        if hallucinated:
            notes.append("Co dau hieu suy doan ngoai tai lieu")

        return {
            "Correctness": correctness,
            "Groundedness": groundedness,
            "Completeness": completeness,
            "RetrievalQuality": retrieval,
            "FormatHandling": fmt,
            "HallucinationRisk": hallucination_score,
            "Conclusion": conclusion,
            "ErrorNote": "; ".join(notes),
        }

    def run(self) -> list[dict[str, object]]:
        self.build_cases()
        results: list[dict[str, object]] = []
        for index, case in enumerate(self.cases, start=1):
            latency, response = self.ask(str(case["question"]), case.get("selected"))  # type: ignore[arg-type]
            answer = str(response.get("answer") or "")
            sources = [str(item) for item in list(response.get("sources") or [])]
            evaluation = self.evaluate(case, answer, sources)
            row = {
                "STT": index,
                "TestID": case["id"],
                "Group": case["group"],
                "File": case["file"],
                "Type": case["type"],
                "Question": case["question"],
                "Expected": case["expected"],
                "Actual": compact_answer(answer),
                "Sources": " | ".join(sources),
                "LatencySec": round(latency, 3),
                **evaluation,
            }
            results.append(row)
            print(
                f"{index:02d}/{len(self.cases)} {case['id']} {row['Conclusion']} "
                f"C{row['Correctness']} R{row['RetrievalQuality']} {latency:.2f}s :: {compact_answer(answer, 120)}",
                flush=True,
            )
            time.sleep(0.35)
        return results


def main() -> None:
    runner = AuditRunner()
    results = runner.run()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "manual_qa_results_clean.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (OUT_DIR / "manual_qa_results_clean.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    summary = Counter(row["Conclusion"] for row in results)
    by_type: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in results:
        by_type[str(row["Type"])].append(row)
    print("\nSUMMARY", dict(summary), "total", len(results), flush=True)
    for file_type, rows in sorted(by_type.items()):
        passed = sum(1 for row in rows if row["Conclusion"] == "Pass")
        avg_correctness = sum(int(row["Correctness"]) for row in rows) / len(rows)
        print(f"TYPE {file_type} total {len(rows)} pass {passed} avgC {avg_correctness:.2f}", flush=True)


if __name__ == "__main__":
    main()
