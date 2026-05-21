# Improvement Plan

## Fix đã triển khai sau audit
- Siết fallback cho câu hỏi kiểm tra sự tồn tại của chủ đề, ví dụ “có thông tin về blockchain không?”, để hệ thống trả lời không tìm thấy khi topic không có trong context.
- Bổ sung nhánh trả lời trực tiếp cho câu hỏi Excel theo “dòng N”, dùng `structured_rows` + `sheet_name` thay vì để LLM tự suy luận từ chunk bảng.
- Bổ sung nhánh trả lời trực tiếp cho câu hỏi “slide N nói về gì / tiêu đề là gì”, đồng thời lọc citation đúng slide.
- Cho FAISS metadata filter nhận diện tên file gốc qua `document_name` / basename, tránh miss khi `source` trong index có prefix upload hash.
- Thêm lọc citation theo row number cho câu hỏi bảng có “dòng N”.

## Xác minh sau fix
- Unit/regression: `230 passed, 3 warnings`.
- Docker: đã copy code vào container `aichatbox-api`, restart thành công, container healthy.
- Smoke test thực tế trong container:
  - Excel dòng 3 `file_excel_mau_song_xanh.xlsx`: trả đúng các trường của dòng 3 và citation sheet `Du_lieu_chien_dich`.
  - Slide 1 `AI Document Question Answering System.pptx`: trả đúng nội dung slide 1, citation chỉ còn slide 1.
  - Negative `blockchain`: fallback đúng, không bịa câu trả lời.

## P0 - Critical / High
- **NEG-019 - noi_dung_mau_thanh_pho_xanh.pdf**: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu. Fix: Siết missing-evidence gate và prompt fallback cho câu hỏi không có thông tin.
- **NEG-002 - bai_trinh_chieu_mau_thu_vien_thong_minh.pptx**: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu. Fix: Bổ sung metadata slide/title/shape, ưu tiên slide filter và citation theo slide.
- **NEG-001 - AI Document Question Answering System.pptx**: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu. Fix: Bổ sung metadata slide/title/shape, ưu tiên slide filter và citation theo slide.
- **NEG-020 - pdf_01_nang_luong_mat_troi.pdf**: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu. Fix: Siết missing-evidence gate và prompt fallback cho câu hỏi không có thông tin.
- **NEG-005 - bao_cao_quan_ly_rac_thai_nhua.pdf**: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu. Fix: Siết missing-evidence gate và prompt fallback cho câu hỏi không có thông tin.
- **NEG-010 - infographic_mau_an_toan_mang.png**: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu. Fix: Rà soát OCR/Vision extraction và metadata ảnh; tăng kiểm tra fallback cho câu hỏi ảnh.
- **NEG-015 - ke_hoach_mau_du_lich_da_lat.md**: Có dấu hiệu suy đoán hoặc trả lời ngoài tài liệu. Fix: Siết missing-evidence gate và prompt fallback cho câu hỏi không có thông tin.
- **DIR-044 - pdf_page_index.md**: Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. Fix: Kiểm tra chunking/retrieval/reranking và ngưỡng fallback cho file liên quan.
- **TAB-013 - file_excel_mau_song_xanh.xlsx**: Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. Fix: Tăng structured extraction cho Excel/bảng, giữ header/sheet/row metadata và ưu tiên table retriever.
- **DIR-078 - Test xlsx.xlsx**: Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. Fix: Tăng structured extraction cho Excel/bảng, giữ header/sheet/row metadata và ưu tiên table retriever.
- **DIR-090 - Test xlsx.xlsx**: Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. Fix: Tăng structured extraction cho Excel/bảng, giữ header/sheet/row metadata và ưu tiên table retriever.
- **DIR-018 - file_excel_mau_song_xanh.xlsx**: Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. Fix: Tăng structured extraction cho Excel/bảng, giữ header/sheet/row metadata và ưu tiên table retriever.

## P1 - Retrieval / Citation
- Thêm unit test cho citation theo page/slide/sheet/row khi câu hỏi có location hint.
- Thêm scoring bắt buộc mỗi selected document có ít nhất một context khi hỏi so sánh.
- Gắn metadata `content_type` nhất quán cho OCR, slide image, spreadsheet row/table.

## P2 - Format Robustness
- **PPTX**: avg_score=0.28, fail=34, hallucination=2. Còn yếu, cần ưu tiên cải thiện parser/retrieval.
- **XLSX**: avg_score=0.33, fail=37, hallucination=0. Còn yếu, cần ưu tiên cải thiện parser/retrieval.
- **JPG**: avg_score=0.73, fail=6, hallucination=0. Còn yếu, cần ưu tiên cải thiện parser/retrieval.
- **MD**: avg_score=0.75, fail=4, hallucination=1. Tương đối ổn, cần rà soát các case sai/citation.
- **PNG**: avg_score=0.75, fail=6, hallucination=1. Tương đối ổn, cần rà soát các case sai/citation.
- **JPEG**: avg_score=0.76, fail=5, hallucination=0. Tương đối ổn, cần rà soát các case sai/citation.
- **PDF**: avg_score=0.79, fail=5, hallucination=3. Tương đối ổn, cần rà soát các case sai/citation.
- **TXT**: avg_score=0.89, fail=0, hallucination=0. Tương đối ổn, cần rà soát các case sai/citation.
- **DOCX**: avg_score=0.90, fail=0, hallucination=0. Hoạt động tốt trong bộ test.

## P3 - Continuous Evaluation
- Lưu bộ 300 case này làm regression dataset.
- Chạy lại sau mỗi thay đổi parser/chunking/retrieval.
- Tách thêm benchmark Hit@1/Hit@5/MRR từ expected source metadata.
