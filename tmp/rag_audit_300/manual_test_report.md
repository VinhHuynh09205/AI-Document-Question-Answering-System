# Manual Test Report - AI Document Chat/RAG

> Ghi chú: Các chỉ số bên dưới là kết quả audit thực tế trước khi vá lỗi. Sau audit, hệ thống đã được fix các lỗi ưu tiên cao về fallback topic không tồn tại, Excel row lookup, slide lookup/citation và source filename matching. Kết quả smoke test sau fix đã được ghi trong `improvement_plan.md`.

## A. Tổng quan kiểm thử

- **Tổng số file đã test:** 43
- **Tổng số câu hỏi:** 300
- **Các loại file đã test:** DOCX, JPEG, JPG, MD, PDF, PNG, PPTX, TXT, XLSX
- **File Ingestion Success Rate:** 100.00%
- **Answer Accuracy:** 149/300 = 49.67%
- **Partial Accuracy:** 56/300 = 18.67%
- **Fail Count:** 95
- **Retrieval Correctness:** 203/300 = 67.67%
- **Citation Correctness:** 203/300 = 67.67%
- **Hallucination Rate:** 7/115 = 6.09%
- **No Answer Correctness:** 13/20 = 65.00%
- **Mean Latency:** 6691.10 ms

### File ingestion

| File | Loại | Chunks | Ingest | Ghi chú |
|---|---:|---:|---|---|
| AI Document Question Answering System.pptx | PPTX | 14 | Pass | Có chunk và metadata truy xuất. |
| bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | PPTX | 25 | Pass | Có chunk và metadata truy xuất. |
| bao_cao_an_toan_du_lieu_ca_nhan.docx | DOCX | 6 | Pass | Có chunk và metadata truy xuất. |
| bao_cao_mau_chuyen_doi_so_giao_duc.pdf | PDF | 15 | Pass | Có chunk và metadata truy xuất. |
| bao_cao_quan_ly_rac_thai_nhua.pdf | PDF | 3 | Pass | Có chunk và metadata truy xuất. |
| content_summary.md | MD | 72 | Pass | Có chunk và metadata truy xuất. |
| docx_01_thu_vien_so.docx | DOCX | 7 | Pass | Có chunk và metadata truy xuất. |
| docx_02_ca_phe_sach.docx | DOCX | 7 | Pass | Có chunk và metadata truy xuất. |
| file_excel_mau_song_xanh.xlsx | XLSX | 41 | Pass | Có chunk và metadata truy xuất. |
| infographic_mau_an_toan_mang.png | PNG | 1 | Pass | Có chunk và metadata truy xuất. |
| jpeg_01_ke_hoach_du_lich.jpeg | JPEG | 1 | Pass | Có chunk và metadata truy xuất. |
| jpeg_02_bang_an_toan_bep.jpeg | JPEG | 1 | Pass | Có chunk và metadata truy xuất. |
| jpg_01_infographic_giac_ngu.jpg | JPG | 1 | Pass | Có chunk và metadata truy xuất. |
| jpg_02_so_do_lop_hoc.jpg | JPG | 1 | Pass | Có chunk và metadata truy xuất. |
| ke_hoach_mau_du_lich_da_lat.md | MD | 12 | Pass | Có chunk và metadata truy xuất. |
| md_01_workshop_thuyet_trinh.md | MD | 4 | Pass | Có chunk và metadata truy xuất. |
| md_02_app_chi_tieu.md | MD | 4 | Pass | Có chunk và metadata truy xuất. |
| nhat_ky_mau_vuon_rau_do_thi.txt | TXT | 11 | Pass | Có chunk và metadata truy xuất. |
| noi_dung_mau_thanh_pho_xanh.pdf | PDF | 2 | Pass | Có chunk và metadata truy xuất. |
| pdf_01_nang_luong_mat_troi.pdf | PDF | 2 | Pass | Có chunk và metadata truy xuất. |
| pdf_02_an_toan_du_lieu.pdf | PDF | 2 | Pass | Có chunk và metadata truy xuất. |
| pdf_page_index.md | MD | 45 | Pass | Có chunk và metadata truy xuất. |
| png_01_ban_do_y_tuong.png | PNG | 1 | Pass | Có chunk và metadata truy xuất. |
| png_02_quy_trinh_giao_hang.png | PNG | 1 | Pass | Có chunk và metadata truy xuất. |
| poster_mau_nang_luong_tai_tao.jpg | JPG | 1 | Pass | Có chunk và metadata truy xuất. |
| pptx_01_du_lich_can_tho.pptx | PPTX | 13 | Pass | Có chunk và metadata truy xuất. |
| pptx_02_trong_cay_truong_hoc.pptx | PPTX | 13 | Pass | Có chunk và metadata truy xuất. |
| RETRIEVAL_TESTING_QUESTION_SET.md | MD | 23 | Pass | Có chunk và metadata truy xuất. |
| storyboard_mau_suc_khoe_hoc_duong.jpeg | JPEG | 1 | Pass | Có chunk và metadata truy xuất. |
| Test docx.docx | DOCX | 136 | Pass | Có chunk và metadata truy xuất. |
| Test jpeg.jpeg | JPEG | 1 | Pass | Có chunk và metadata truy xuất. |
| Test JPG.jpg | JPG | 1 | Pass | Có chunk và metadata truy xuất. |
| Test md.md | MD | 61 | Pass | Có chunk và metadata truy xuất. |
| Test pdf scan.pdf | PDF | 3 | Pass | Có chunk và metadata truy xuất. |
| Test pdf.pdf | PDF | 37 | Pass | Có chunk và metadata truy xuất. |
| Test PNG.png | PNG | 1 | Pass | Có chunk và metadata truy xuất. |
| Test pptx.pptx | PPTX | 43 | Pass | Có chunk và metadata truy xuất. |
| test txt.txt | TXT | 12 | Pass | Có chunk và metadata truy xuất. |
| Test xlsx.xlsx | XLSX | 48 | Pass | Có chunk và metadata truy xuất. |
| txt_01_nhat_ky_vuon_rau.txt | TXT | 2 | Pass | Có chunk và metadata truy xuất. |
| txt_02_ke_hoach_clb_sach.txt | TXT | 2 | Pass | Có chunk và metadata truy xuất. |
| xlsx_01_bao_cao_doanh_thu.xlsx | XLSX | 5 | Pass | Có chunk và metadata truy xuất. |
| xlsx_02_ke_hoach_hoc_tap.xlsx | XLSX | 6 | Pass | Có chunk và metadata truy xuất. |

## B. Bảng kết quả chi tiết 300 câu hỏi

Bảng đầy đủ nằm trong `manual_test_report.xlsx`. Dưới đây là 40 dòng đầu và toàn bộ lỗi nằm trong `failed_cases.csv`.

| ID | File | Nhóm | Retrieval | Citation | Điểm | Hallucination | Mức độ lỗi | Ghi chú |
|---|---|---|---|---|---:|---|---|---|
| DIR-001 | AI Document Question Answering System.pptx | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-002 | AI Document Question Answering System.pptx | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-003 | bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-004 | bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-005 | bao_cao_an_toan_du_lieu_ca_nhan.docx | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-006 | bao_cao_an_toan_du_lieu_ca_nhan.docx | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-007 | bao_cao_mau_chuyen_doi_so_giao_duc.pdf | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-008 | bao_cao_mau_chuyen_doi_so_giao_duc.pdf | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-009 | bao_cao_quan_ly_rac_thai_nhua.pdf | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-010 | bao_cao_quan_ly_rac_thai_nhua.pdf | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-011 | content_summary.md | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-012 | content_summary.md | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-013 | docx_01_thu_vien_so.docx | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-014 | docx_01_thu_vien_so.docx | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-015 | docx_02_ca_phe_sach.docx | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-016 | docx_02_ca_phe_sach.docx | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-017 | file_excel_mau_song_xanh.xlsx | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-018 | file_excel_mau_song_xanh.xlsx | Direct | Sai | Sai | 0.0 | Không | High | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc th |
| DIR-019 | infographic_mau_an_toan_mang.png | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-020 | infographic_mau_an_toan_mang.png | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-021 | jpeg_01_ke_hoach_du_lich.jpeg | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-022 | jpeg_01_ke_hoach_du_lich.jpeg | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-023 | jpeg_02_bang_an_toan_bep.jpeg | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-024 | jpeg_02_bang_an_toan_bep.jpeg | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-025 | jpg_01_infographic_giac_ngu.jpg | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-026 | jpg_01_infographic_giac_ngu.jpg | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-027 | jpg_02_so_do_lop_hoc.jpg | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-028 | jpg_02_so_do_lop_hoc.jpg | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-029 | ke_hoach_mau_du_lich_da_lat.md | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-030 | ke_hoach_mau_du_lich_da_lat.md | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-031 | md_01_workshop_thuyet_trinh.md | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-032 | md_01_workshop_thuyet_trinh.md | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-033 | md_02_app_chi_tieu.md | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-034 | md_02_app_chi_tieu.md | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-035 | nhat_ky_mau_vuon_rau_do_thi.txt | Direct | Đúng | Đúng | 0.5 | Không | Medium | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-036 | nhat_ky_mau_vuon_rau_do_thi.txt | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-037 | noi_dung_mau_thanh_pho_xanh.pdf | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-038 | noi_dung_mau_thanh_pho_xanh.pdf | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-039 | pdf_01_nang_luong_mat_troi.pdf | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| DIR-040 | pdf_01_nang_luong_mat_troi.pdf | Direct | Đúng | Đúng | 1.0 | Không | None | Đạt kỳ vọng theo bộ từ khóa chuẩn. |

## C. Phân tích lỗi theo loại file

| Loại file | Số case | Điểm TB | Full correct | Partial | Fail | Hallucination | Nhận xét |
|---|---:|---:|---:|---:|---:|---:|---|
| DOCX | 25 | 0.90 | 20 | 5 | 0 | 0 | Hoạt động tốt trong bộ test. |
| JPEG | 25 | 0.76 | 18 | 2 | 5 | 0 | Tương đối ổn, cần rà soát các case sai/citation. |
| JPG | 28 | 0.73 | 19 | 3 | 6 | 0 | Còn yếu, cần ưu tiên cải thiện parser/retrieval. |
| MD | 46 | 0.75 | 27 | 15 | 4 | 1 | Tương đối ổn, cần rà soát các case sai/citation. |
| PDF | 42 | 0.79 | 29 | 8 | 5 | 3 | Tương đối ổn, cần rà soát các case sai/citation. |
| PNG | 28 | 0.75 | 20 | 2 | 6 | 1 | Tương đối ổn, cần rà soát các case sai/citation. |
| PPTX | 62 | 0.28 | 7 | 21 | 34 | 2 | Còn yếu, cần ưu tiên cải thiện parser/retrieval. |
| TXT | 23 | 0.89 | 18 | 5 | 0 | 0 | Tương đối ổn, cần rà soát các case sai/citation. |
| XLSX | 61 | 0.33 | 16 | 8 | 37 | 0 | Còn yếu, cần ưu tiên cải thiện parser/retrieval. |

## D. Top lỗi nghiêm trọng nhất

1. **Critical - NEG-019 (noi_dung_mau_thanh_pho_xanh.pdf)**
   - Câu hỏi: Trong file "noi_dung_mau_thanh_pho_xanh.pdf" có thông tin về luong nhan vien không?
   - Trả lời hệ thống: bản, bảng và bố cục cơ bản trong một file PDF. Tài liệu PDF mẫu này có nội dung ngẫu nhiên, dùng để kiểm tra khả năng hiển thị văn.
   - Nguyên nhân/ghi chú: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu.
   - Đề xuất: Siết missing-evidence gate và prompt fallback cho câu hỏi không có thông tin.

2. **Critical - NEG-002 (bai_trinh_chieu_mau_thu_vien_thong_minh.pptx)**
   - Câu hỏi: Trong file "bai_trinh_chieu_mau_thu_vien_thong_minh.pptx" có thông tin về mat khau admin không?
   - Trả lời hệ thống: Luồng này giúp kiểm thử file PPTX vì mỗi bước có tiêu đề, mô tả và vị trí trực quan riêng. Lưu thông tin sách, tác giả, thể loại, vị trí kệ, trạng thái mượn và lịch sử cập nhật. Kết luận: thư viện cần được số hóa theo hướng dễ dùng, có dữ liệu tập trung và hỗ trợ tìm kiếm thông minh. File PPTX mẫu •
   - Nguyên nhân/ghi chú: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu.
   - Đề xuất: Bổ sung metadata slide/title/shape, ưu tiên slide filter và citation theo slide.

3. **Critical - NEG-001 (AI Document Question Answering System.pptx)**
   - Câu hỏi: Trong file "AI Document Question Answering System.pptx" có thông tin về blockchain không?
   - Trả lời hệ thống: AI Document Question Answering System ĐỀ TÀI: AI Document Question Answering System.
   - Nguyên nhân/ghi chú: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu.
   - Đề xuất: Bổ sung metadata slide/title/shape, ưu tiên slide filter và citation theo slide.

4. **Critical - NEG-020 (pdf_01_nang_luong_mat_troi.pdf)**
   - Câu hỏi: Trong file "pdf_01_nang_luong_mat_troi.pdf" có thông tin về thong tin bao hiem không?
   - Trả lời hệ thống: Bảng thông tin kiểm thử.
   - Nguyên nhân/ghi chú: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu.
   - Đề xuất: Siết missing-evidence gate và prompt fallback cho câu hỏi không có thông tin.

5. **Critical - NEG-005 (bao_cao_quan_ly_rac_thai_nhua.pdf)**
   - Câu hỏi: Trong file "bao_cao_quan_ly_rac_thai_nhua.pdf" có thông tin về gia co phieu Apple không?
   - Trả lời hệ thống: Tài liệu PDF mẫu này trình bày một vấn đề môi trường khác với file DOCX: cách quản lý file PDF. Nhựa khó phân hủy, có thể tồn tại trong môi trường rất lâu.
   - Nguyên nhân/ghi chú: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu.
   - Đề xuất: Siết missing-evidence gate và prompt fallback cho câu hỏi không có thông tin.

6. **Critical - NEG-010 (infographic_mau_an_toan_mang.png)**
   - Câu hỏi: Trong file "infographic_mau_an_toan_mang.png" có thông tin về hop dong lao dong không?
   - Trả lời hệ thống: Noi dung minh hoa dai hon, dung de kiem thu nhan dien chu trong anh PNG. Noi dung minh hoa dai hon, dung de kiem thu nhan dien chu trong anh PNG.
   - Nguyên nhân/ghi chú: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu.
   - Đề xuất: Rà soát OCR/Vision extraction và metadata ảnh; tăng kiểm tra fallback cho câu hỏi ảnh.

7. **Critical - NEG-015 (ke_hoach_mau_du_lich_da_lat.md)**
   - Câu hỏi: Trong file "ke_hoach_mau_du_lich_da_lat.md" có thông tin về so dien thoai ca nhan không?
   - Trả lời hệ thống: Số điện thoại trong tài liệu: 250000300000.
   - Nguyên nhân/ghi chú: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu.
   - Đề xuất: Siết missing-evidence gate và prompt fallback cho câu hỏi không có thông tin.

8. **High - DIR-044 (pdf_page_index.md)**
   - Câu hỏi: Nêu một thông tin cụ thể xuất hiện trong file "pdf_page_index.md".
   - Trả lời hệ thống: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
   - Nguyên nhân/ghi chú: Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn.
   - Đề xuất: Kiểm tra chunking/retrieval/reranking và ngưỡng fallback cho file liên quan.

9. **High - TAB-013 (file_excel_mau_song_xanh.xlsx)**
   - Câu hỏi: Trong file "file_excel_mau_song_xanh.xlsx", ở sheet "Du_lieu_chien_dich", dòng 14 có thông tin gì?
   - Trả lời hệ thống: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
   - Nguyên nhân/ghi chú: Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn.
   - Đề xuất: Tăng structured extraction cho Excel/bảng, giữ header/sheet/row metadata và ưu tiên table retriever.

10. **High - DIR-078 (Test xlsx.xlsx)**
   - Câu hỏi: Nêu một thông tin cụ thể xuất hiện trong file "Test xlsx.xlsx".
   - Trả lời hệ thống: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
   - Nguyên nhân/ghi chú: Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn.
   - Đề xuất: Tăng structured extraction cho Excel/bảng, giữ header/sheet/row metadata và ưu tiên table retriever.


## E. Đề xuất cải thiện hệ thống

- **File parser:** thêm regression fixture cho từng định dạng và so sánh số chunk/metadata sau mỗi lần sửa.
- **OCR/Vision:** tăng kiểm thử ảnh nhiễu, ảnh nhiều chữ, PDF scan; lưu OCR confidence nếu provider hỗ trợ.
- **Excel extraction:** giữ đầy đủ sheet/header/row/range/formula cached value; ưu tiên structured table answer cho câu hỏi số liệu.
- **PPTX extraction:** tăng metadata slide/title/shape/table/image; citation theo slide phải ưu tiên đúng slide được hỏi.
- **Chunking:** kiểm soát chunk không cắt mất heading/bảng; bổ sung parent metadata cho các chunk con.
- **Metadata:** chuẩn hóa source, page, slide, sheet, row_index, content_type để citation ổn định.
- **Embedding:** tiếp tục dùng MiniLM-L12-v2 cho độ trễ thấp; cân nhắc A/B với model mạnh hơn cho OCR và tiếng Nhật.
- **Retrieval/reranking:** bảo toàn context theo từng tài liệu khi multi-select; thêm reranker chuyên cho bảng/slide.
- **Citation:** giới hạn nguồn theo câu hỏi cụ thể; loại citation trùng và nguồn nhiễu.
- **Prompt/fallback:** giữ nguyên tắc trả lời ngắn, không bịa; negative question phải trả lời không tìm thấy khi thiếu bằng chứng.
