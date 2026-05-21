# Unified 450-Question Audit

## Summary

| Metric | Value |
|---|---:|
| total_files | 43 |
| total_questions | 450 |
| full_correct | 252 |
| partial_correct | 134 |
| fail | 64 |
| full_accuracy | 0.56 |
| accepted_count | 386 |
| accepted_rate | 0.8578 |
| retrieval_correct | 377 |
| retrieval_rate | 0.8378 |
| citation_correct | 377 |
| citation_rate | 0.8378 |
| hallucination_count | 0 |
| hallucination_rate | 0.0 |
| mean_latency_ms | 2276.23 |

## Question Groups

| Group | Count |
|---|---:|
| Additional 45 | 45 |
| Base 300 | 300 |
| Focused Regression | 65 |
| Postfix Extra | 40 |

## Cases To Review

| ID | File | Score | Retrieval | Citation | Hallucination | Notes |
|---|---|---:|---|---|---|---|
| B300-DIR-001 | AI Document Question Answering System.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-002 | AI Document Question Answering System.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-003 | bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-004 | bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-011 | content_summary.md | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-012 | content_summary.md | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-013 | docx_01_thu_vien_so.docx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-014 | docx_01_thu_vien_so.docx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-016 | docx_02_ca_phe_sach.docx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-018 | file_excel_mau_song_xanh.xlsx | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-019 | infographic_mau_an_toan_mang.png | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-020 | infographic_mau_an_toan_mang.png | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-022 | jpeg_01_ke_hoach_du_lich.jpeg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-023 | jpeg_02_bang_an_toan_bep.jpeg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-024 | jpeg_02_bang_an_toan_bep.jpeg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-025 | jpg_01_infographic_giac_ngu.jpg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-026 | jpg_01_infographic_giac_ngu.jpg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-027 | jpg_02_so_do_lop_hoc.jpg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-028 | jpg_02_so_do_lop_hoc.jpg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-032 | md_01_workshop_thuyet_trinh.md | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-033 | md_02_app_chi_tieu.md | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-034 | md_02_app_chi_tieu.md | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-040 | pdf_01_nang_luong_mat_troi.pdf | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-042 | pdf_02_an_toan_du_lieu.pdf | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-043 | pdf_page_index.md | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-044 | pdf_page_index.md | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-045 | png_01_ban_do_y_tuong.png | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-046 | png_01_ban_do_y_tuong.png | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-047 | png_02_quy_trinh_giao_hang.png | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-048 | png_02_quy_trinh_giao_hang.png | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-050 | poster_mau_nang_luong_tai_tao.jpg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-051 | pptx_01_du_lich_can_tho.pptx | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-052 | pptx_01_du_lich_can_tho.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-053 | pptx_02_trong_cay_truong_hoc.pptx | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-054 | pptx_02_trong_cay_truong_hoc.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-055 | RETRIEVAL_TESTING_QUESTION_SET.md | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-057 | storyboard_mau_suc_khoe_hoc_duong.jpeg | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-058 | storyboard_mau_suc_khoe_hoc_duong.jpeg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-061 | Test jpeg.jpeg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-062 | Test jpeg.jpeg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-063 | Test JPG.jpg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-064 | Test JPG.jpg | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-065 | Test md.md | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-068 | Test pdf scan.pdf | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-069 | Test pdf.pdf | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-070 | Test pdf.pdf | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-071 | Test PNG.png | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-072 | Test PNG.png | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-073 | Test pptx.pptx | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-074 | Test pptx.pptx | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-075 | test txt.txt | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-077 | Test xlsx.xlsx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-078 | Test xlsx.xlsx | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-079 | txt_01_nhat_ky_vuon_rau.txt | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-082 | txt_02_ke_hoach_clb_sach.txt | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-084 | xlsx_01_bao_cao_doanh_thu.xlsx | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-DIR-086 | xlsx_02_ke_hoach_hoc_tap.xlsx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-088 | content_summary.md | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-089 | Test md.md | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-DIR-090 | Test xlsx.xlsx | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-SUM-001 | AI Document Question Answering System.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-SUM-002 | bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-SUM-006 | content_summary.md | 0.5 | Đúng | Đúng | Không | Có sinh sơ đồ/mermaid khi câu hỏi không yêu cầu rõ. |
| B300-SUM-033 | Test md.md | 0.5 | Đúng | Đúng | Không | Có sinh sơ đồ/mermaid khi câu hỏi không yêu cầu rõ. |
| B300-SUM-035 | Test pdf.pdf | 0.5 | Đúng | Đúng | Không | Có sinh sơ đồ/mermaid khi câu hỏi không yêu cầu rõ. |
| B300-SUM-047 | Test xlsx.xlsx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-SUM-048 | pdf_page_index.md | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-SUM-051 | Test pdf.pdf | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-SUM-052 | bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-SUM-055 | AI Document Question Answering System.pptx | 0.5 | Đúng | Đúng | Không | Có sinh sơ đồ/mermaid khi câu hỏi không yêu cầu rõ. |
| B300-SUM-056 | pptx_01_du_lich_can_tho.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-SUM-057 | pptx_02_trong_cay_truong_hoc.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-CMP-001 | bao_cao_an_toan_du_lieu_ca_nhan.docx, Test jpeg.jpeg | 0.5 | Một phần | Một phần | Không | Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-CMP-004 | Test docx.docx, poster_mau_nang_luong_tai_tao.jpg | 0.5 | Một phần | Một phần | Không | Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-CMP-011 | poster_mau_nang_luong_tai_tao.jpg, RETRIEVAL_TESTING_QUESTION_SET.md | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-CMP-012 | Test JPG.jpg, Test md.md | 0.5 | Một phần | Một phần | Không | Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-CMP-018 | RETRIEVAL_TESTING_QUESTION_SET.md, Test pdf scan.pdf | 0.0 | Sai | Sai | Không | Fallback dù case có đáp án kỳ vọng. Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| B300-CMP-019 | Test md.md, Test pdf.pdf | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-CMP-024 | pdf_02_an_toan_du_lieu.pdf, AI Document Question Answering System.pptx | 0.5 | Đúng | Đúng | Không | Đạt kỳ vọng theo bộ từ khóa chuẩn. |
| B300-CMP-025 | Test pdf scan.pdf, bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | 0.5 | Một phần | Một phần | Không | Citation không bao phủ đúng file kỳ vọng. Retrieval/citation có dấu hiệu sai hoặc thiếu nguồn. |
| ... | ... | ... | ... | ... | ... | Con 118 case trong CSV |