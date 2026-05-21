# Bao cao kiem thu AI Document Chat/RAG - manual_test_files

- Thu muc test: `C:/AIChatBox/tmp/manual_test_files`
- Workspace test: `85f9512b918e4a7383d2fc217d4f5334`
- Tong file upload: 25
- Tong chunk indexed: 615
- Tong cau hoi test: 65
- Pass: 43
- Fail: 22
- Accuracy reviewed: 66.15%
- Hallucination/scope-risk cases: 2/65 (3.08%)

## 1. File va ingestion

| STT | File | Chunks | Content types | Nhan xet ingestion |
|---:|---|---:|---|---|
| 1 | AI Document Question Answering System.pptx | 14 | slide_chunk:10, slide_block_chunk:4 | Slide/chunk co metadata, nhung cau tong quan/slide title co luc lay sai |
| 2 | bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | 25 | slide_block_chunk:25 | Slide/chunk co metadata, nhung cau tong quan/slide title co luc lay sai |
| 3 | bao_cao_an_toan_du_lieu_ca_nhan.docx | 6 | docx_page:6 | OK |
| 4 | bao_cao_mau_chuyen_doi_so_giao_duc.pdf | 15 | pdf_page:15 | PDF text doc duoc; bang trong PDF bi flatten, truy xuat so lieu bang con yeu |
| 5 | bao_cao_quan_ly_rac_thai_nhua.pdf | 3 | pdf_page:3 | PDF text doc duoc; bang trong PDF bi flatten, truy xuat so lieu bang con yeu |
| 6 | content_summary.md | 72 | text:72 | Text/heading doc duoc; metadata content_type con trong voi MD/TXT |
| 7 | file_excel_mau_song_xanh.xlsx | 41 | spreadsheet_sheet_summary:2, spreadsheet_table_chunk:39 | Sheet/header/formula duoc ingest, QA truy xuat bang con yeu |
| 8 | infographic_mau_an_toan_mang.png | 1 | image_document:1 | OCR/Vision co doc duoc chu, nhung mat dau/loi OCR o anh moi va poster/storyboard |
| 9 | ke_hoach_mau_du_lich_da_lat.md | 12 | text:12 | Text/heading doc duoc; metadata content_type con trong voi MD/TXT |
| 10 | nhat_ky_mau_vuon_rau_do_thi.txt | 11 | text:11 | Text/heading doc duoc; metadata content_type con trong voi MD/TXT |
| 11 | noi_dung_mau_thanh_pho_xanh.pdf | 2 | pdf_page:2 | PDF text doc duoc; bang trong PDF bi flatten, truy xuat so lieu bang con yeu |
| 12 | pdf_page_index.md | 45 | text:45 | Text/heading doc duoc; metadata content_type con trong voi MD/TXT |
| 13 | poster_mau_nang_luong_tai_tao.jpg | 1 | image_document:1 | OCR/Vision co doc duoc chu, nhung mat dau/loi OCR o anh moi va poster/storyboard |
| 14 | RETRIEVAL_TESTING_QUESTION_SET.md | 23 | text:23 | Text/heading doc duoc; metadata content_type con trong voi MD/TXT |
| 15 | storyboard_mau_suc_khoe_hoc_duong.jpeg | 1 | image_document:1 | OCR/Vision co doc duoc chu, nhung mat dau/loi OCR o anh moi va poster/storyboard |
| 16 | Test docx.docx | 136 | docx_page:136 | OK |
| 17 | Test jpeg.jpeg | 1 | image_document:1 | OCR/Vision co doc duoc chu, nhung mat dau/loi OCR o anh moi va poster/storyboard |
| 18 | Test JPG.jpg | 1 | image_document:1 | OCR/Vision co doc duoc chu, nhung mat dau/loi OCR o anh moi va poster/storyboard |
| 19 | Test md.md | 61 | text:61 | Text/heading doc duoc; metadata content_type con trong voi MD/TXT |
| 20 | Test pdf scan.pdf | 3 | pdf_page:3 | PDF text doc duoc; bang trong PDF bi flatten, truy xuat so lieu bang con yeu |
| 21 | Test pdf.pdf | 37 | pdf_page:37 | PDF text doc duoc; bang trong PDF bi flatten, truy xuat so lieu bang con yeu |
| 22 | Test PNG.png | 1 | image_document:1 | OCR/Vision co doc duoc chu, nhung mat dau/loi OCR o anh moi va poster/storyboard |
| 23 | Test pptx.pptx | 43 | slide_chunk:40, slide_structured:3 | Slide/chunk co metadata, nhung cau tong quan/slide title co luc lay sai |
| 24 | test txt.txt | 12 | text:12 | Text/heading doc duoc; metadata content_type con trong voi MD/TXT |
| 25 | Test xlsx.xlsx | 48 | spreadsheet_sheet_summary:3, spreadsheet_table_chunk:45 | Sheet/header/formula duoc ingest, QA truy xuat bang con yeu |

## 2. Tong hop theo nhom cau hoi

| Nhom | Total | Pass | Fail | Pass rate |
|---|---:|---:|---:|---:|
| A-Direct | 23 | 16 | 7 | 69.57% |
| B-Detail | 25 | 18 | 7 | 72.00% |
| C-Summary | 3 | 2 | 1 | 66.67% |
| D-Cross | 3 | 0 | 3 | 0.00% |
| E-Format | 2 | 0 | 2 | 0.00% |
| F-Negative | 4 | 4 | 0 | 100.00% |
| G-Ambiguous | 2 | 1 | 1 | 50.00% |
| H-Distractor | 3 | 2 | 1 | 66.67% |

## 3. Tong hop theo loai file

| Loai file | Total cases | Pass | Fail | Avg Correctness | Avg latency(s) |
|---|---:|---:|---:|---:|---:|
| DOCX | 4 | 2 | 2 | 2.75/5 | 12.27 |
| JPEG | 5 | 5 | 0 | 5.00/5 | 11.54 |
| JPG | 5 | 4 | 1 | 4.00/5 | 8.13 |
| MD | 11 | 6 | 5 | 2.91/5 | 24.07 |
| MD+JPG | 1 | 0 | 1 | 1.00/5 | 19.44 |
| MIXED | 2 | 1 | 1 | 3.00/5 | 17.95 |
| PDF | 11 | 8 | 3 | 3.73/5 | 16.45 |
| PDF_SCAN | 3 | 3 | 0 | 5.00/5 | 3.56 |
| PNG | 4 | 3 | 1 | 4.00/5 | 9.16 |
| PNG+DOCX | 1 | 0 | 1 | 2.00/5 | 19.47 |
| PPTX | 7 | 5 | 2 | 3.71/5 | 8.69 |
| TXT | 4 | 4 | 0 | 5.00/5 | 25.58 |
| XLSX | 7 | 2 | 5 | 1.86/5 | 1.32 |

## 4. Bang ket qua chi tiet

| STT | ID | File | Type | Cau hoi | Expected | Actual | C | G | Comp | R | Fmt | Hall | Ket luan | Ghi chu |
|---:|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 1 | A01 | AI Document Question Answering System.pptx | PPTX | De tai trong slide dau la gi? | AI Document Question Answering System | De tai trong slide đầu là Luồng hỏi đáp AI/RAG. | 1 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 2 | B01 | AI Document Question Answering System.pptx | PPTX | Giang vien huong dan trong PPTX la ai? | Nguyen Van Huy | Giảng viên hướng dẫn trong PPTX là Nguyễn Văn Huy. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 3 | A02 | bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | PPTX | Bai trinh chieu mau noi ve chu de gi? | Thu vien thong minh cho truong hoc hien dai | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 0 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 4 | B02 | bai_trinh_chieu_mau_thu_vien_thong_minh.pptx | PPTX | Slide 1 co cac nhan chuc nang nao? | Du lieu sach, Tim kiem nhanh, Goi y hoc tap | Slide 1 có các chức năng sau: - LIBRARY - Tìm kiếm nhanh - Gợi ý học tập | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 5 | A03 | bao_cao_an_toan_du_lieu_ca_nhan.docx | DOCX | Tai lieu DOCX nay noi ve van de gi? | An toan du lieu ca nhan trong ung dung so | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 0 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 6 | B03 | bao_cao_an_toan_du_lieu_ca_nhan.docx | DOCX | Cac nguyen nhan thuong gap gay rui ro du lieu la gi? | Mat khau yeu, thieu ma hoa, truy cap sai quyen, thieu quy trinh xoa/an danh | Nguyên nhân thường gặp gây rò rỉ dữ liệu cá nhân là người dùng đặt mật khẩu yếu, hệ thống thiếu mã hóa, nhân viên nội bộ truy cập dữ liệu không đúng quyền, và doanh nghiệp chưa ... | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 7 | A04 | bao_cao_mau_chuyen_doi_so_giao_duc.pdf | PDF | PDF chuyen doi so giao duc noi ve noi dung gi? | Chuyen doi so trong giao duc | Câu hỏi của bạn là: "PDF chuyen doi so giao duc noi ve noi dung gi?" Câu trả lời trực tiếp và đúng trọng tâm là: Chuyển đổi số trong giáo dục không chỉ là việc đưa máy tính hoặc... | 5 | 5 | 5 | 5 | 4 | 5 | Pass | Dung noi dung nhung hoi dai, lap lai cau hoi |
| 8 | B04 | bao_cao_mau_chuyen_doi_so_giao_duc.pdf | PDF | Muc tieu dau tien khi trien khai chuyen doi so giao duc la gi? | Tang hieu qua quan ly | Mục tiêu đầu tiên khi triển khai chuyển đổi số trong giáo dục là tăng hiệu quả quản lý. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 9 | A05 | bao_cao_quan_ly_rac_thai_nhua.pdf | PDF | Bao cao rac thai nhua noi ve van de gi? | Quan ly rac thai nhua tai khu dan cu | Báo cáo về vấn đề rác thải nhựa ở khu dân cư này chủ yếu nói về thực trạng, nguyên nhân và hậu quả của vấn đề này, cũng như kế hoạch hành động đề xuất để giảm thiểu rác thải nhựa. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 10 | B05 | bao_cao_quan_ly_rac_thai_nhua.pdf | PDF | Ke hoach hanh dong de xuat gom nhung hoat dong nao? | Phan loai tai nguon, ngay doi rac lay qua, giam nhua dung mot lan, theo doi so lieu | Để xả ra kế hoạch hành động đề xuất, cần xem xét các hoạt động và kết quả mong đợi được đề xuất trong tài liệu. - Hoạt động: Phân loại tại nguồn, Ngày đổi rác lấy quà, Giảm nhựa... | 5 | 5 | 5 | 5 | 4 | 5 | Pass | Dung noi dung nhung van phong hoi dai va co loi tu "xa ra" |
| 11 | A06 | content_summary.md | MD | File content_summary.md mo ta noi dung gi? | Tong hop/ket qua trich xuat noi dung tai lieu test | 3.3.1. - Độ chính xác và Khả năng kiểm soát ảo giác (Accuracy & Grounding) - Trong pha Offline, hệ thống thực hiện xử lý dữ liệu nguồn từ các văn bản pháp luật (DOCX), trích xuấ... | 1 | 3 | 1 | 5 | 4 | 3 | Fail | Tra loi khong dung trong tam file content_summary; truy xuat dung file nhung sai noi dung can hoi |
| 12 | B06 | content_summary.md | MD | content_summary.md ghi tong so paragraph la bao nhieu? | 346 | Chatbot trí tuệ nhân tạo là một bước tiến vượt bậc so với các chương trình trả lời tự động truyền thống, nhờ khả năng hiểu và xử lý ngôn ngữ tự nhiên để tương tác với con người ... | 1 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 13 | E01 | file_excel_mau_song_xanh.xlsx | XLSX | File Excel song xanh co nhung sheet nao? | Du_lieu_chien_dich va Tong_quan | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 0 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 14 | B07 | file_excel_mau_song_xanh.xlsx | XLSX | Ngay 2026-05-01 co hoat dong gi va o khu vuc nao? | Doi rac lay cay tai Ky tuc xa | Ở Du_lieu_chien_dich, dòng 3, Khu vực: Ký túc xá. | 1 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 15 | A07 | infographic_mau_an_toan_mang.png | PNG | Infographic PNG noi ve chu de gi? | An toan mang cho sinh vien | Infographic PNG này nói về chủ đề "An toàn mạng" cho sinh viên. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 16 | B08 | infographic_mau_an_toan_mang.png | PNG | Infographic neu nhung bien phap an toan mang nao? | Mat khau manh, xac thuc hai lop, canh giac lien ket la, sao luu du lieu | Câu hỏi của bạn là: Infographic neu nhung bien phap an toan mang nao? Dựa trên tài liệu, có 5 biện pháp an toàn mang được đề cập trong infographic: 1. **Mat khau manh** (Mật khẩ... | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 17 | A08 | ke_hoach_mau_du_lich_da_lat.md | MD | Ke hoach Markdown nay noi ve chuyen di nao? | Du lich Da Lat | Ke hoạch Markdown này nói về chuyến đi Đà Lạt. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 18 | B09 | ke_hoach_mau_du_lich_da_lat.md | MD | Nhom gia dinh gom bao nhieu nguoi va di chuyen bang gi? | 4 nguoi, xe khach tu TP.HCM | Nhóm gia đình gồm 4 người. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 19 | A09 | nhat_ky_mau_vuon_rau_do_thi.txt | TXT | Nhat ky TXT noi ve du an gi? | Vuon rau do thi tren san thuong | Dự án vườn rau đô thị trên sân thượng được thực hiện để tạo ra một mô hình sống xanh, giảm lãng phí và giúp mọi người hiểu hơn về quá trình tạo ra thức ăn. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 20 | B10 | nhat_ky_mau_vuon_rau_do_thi.txt | TXT | Dien tich san thuong ban dau khoang bao nhieu? | Khoang 30 met vuong | Diện tích sân thượng ban đầu khoảng 30 mét vuông. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 21 | A10 | noi_dung_mau_thanh_pho_xanh.pdf | PDF | PDF Thanh pho Xanh 2030 huong den muc tieu gi? | Giam rac thai nhua, tang khong gian xanh, di chuyen sach | Mục tiêu chính của Dự án Thành phố Xanh 2030 là giảm rác thải nhựa, tăng không gian xanh và xây dựng thói quen di chuyển sạch như đi bộ, xe đạp hoặc phương tiện công cộng. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 22 | B11 | noi_dung_mau_thanh_pho_xanh.pdf | PDF | Bang so lieu mau trong PDF Thanh pho Xanh co nhung chi so nao? | Cay xanh moi 1.250, rac tai che 8,4 tan, nguoi tham gia 3.600, tuyen xe dap 12 | bản, bảng và bố cục cơ bản trong một file PDF. | 1 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 23 | A11 | pdf_page_index.md | MD | pdf_page_index.md dung de lam gi? | Chi muc/trich xuat theo trang cho PDF thi giac may tinh | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 0 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 24 | B12 | pdf_page_index.md | MD | Trang dau trong pdf_page_index.md nhac toi noi dung gi? | Tong quan ve thi giac may tinh va xu ly anh | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 0 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 25 | A12 | poster_mau_nang_luong_tai_tao.jpg | JPG | Poster JPG noi ve chu de gi? | Nang luong tai tao trong doi song | Poster JPG này nói về chủ đề: "Năng lượng tái tạo trong đời sống". | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 26 | B13 | poster_mau_nang_luong_tai_tao.jpg | JPG | Poster neu nhung loai nang luong nao? | Dien mat troi, dien gio, sinh khoi va tiet kiem nang luong | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 0 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 27 | A13 | RETRIEVAL_TESTING_QUESTION_SET.md | MD | Bo test retrieval nay duoc xay dung de kiem tra gi? | Retrieval theo nguon/noi dung/da ngon ngu/fallback | Câu hỏi: Bo test retrieval nay duoc xay dung de kiem tra gi? Trả lời: Bo test retrieval nay duoc xay dung de kiem tra retrieval, bao gom cac khong gian kiem tra theo nguon, noi ... | 5 | 5 | 5 | 5 | 4 | 5 | Pass | Dung noi dung nhung hoi dai, lap lai cau hoi |
| 28 | B14 | RETRIEVAL_TESTING_QUESTION_SET.md | MD | Bo test nay liet ke nhung file anh nao? | Test JPG.jpg, Test PNG.png, Test jpeg.jpeg | Bo test nay duoc xay dung truc tiep tu bo file trong thu muc: / RQ-PDFSCAN-02 / Test pdf scan.pdf / Co trich duoc email hoac so dien thoai tu file scan nay khong? / RQ-PPTX-04 /... | 1 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 29 | A14 | storyboard_mau_suc_khoe_hoc_duong.jpeg | JPEG | Storyboard JPEG noi ve chu de gi? | Suc khoe hoc duong | Câu hỏi của bạn là "Storyboard JPEG noi ve chu de gi?" (Storyboard JPEG nói về chủ đề gì?). Dựa trên tài liệu, storyboard JPEG này nói về chủ đề "Sức khỏe học đường" (Surc khoe ... | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 30 | B15 | storyboard_mau_suc_khoe_hoc_duong.jpeg | JPEG | Storyboard mo ta bao nhieu canh? | 6 canh | Storyboard mô tả 6 cảnh. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 31 | A15 | Test docx.docx | DOCX | De tai nghien cuu trong bao cao la gi? | Nghien cuu, ung dung mo hinh AI, ket hop do thi tri thuc ho tro tra cuu luat CNTT | Dự án không chỉ đạt được các cột mốc về mặt kỹ thuật mà còn chứng minh được tính thực tiễn cao trong việc hỗ trợ tiếp cận pháp luật số. Thay vì chỉ tìm kiếm theo từ khóa đơn thu... | 1 | 3 | 1 | 5 | 3 | 3 | Fail | Answer mismatch/fallback sai |
| 32 | B16 | Test docx.docx | DOCX | Sinh vien thuc hien la ai? | Huynh Ba Thanh | Sinh viên thực hiện là Huỳnh Bá Thành. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 33 | A16 | Test jpeg.jpeg | JPEG | Anh JPEG bao cao noi dung gi? | Bao cao doanh thu thang 05/2026 | Báo cáo này bao gồm thông tin về doanh thu tháng 05/2026 của một công ty. Báo cáo này bao gồm các thông tin sau: - Doanh thu theo tuần (triệu đồng) - Tổng doanh thu - Số lượng đ... | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 34 | B17 | Test jpeg.jpeg | JPEG | Tong don hang va tong doanh thu la bao nhieu? | 260 don hang, 78.7M | Tổng đơn hàng và tổng doanh thu là 260 và 78.7 triệu đồng. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 35 | A17 | Test JPG.jpg | JPG | Anh JPG OCR test co email lien he nao? | qa-team@example.com | Email liên hệ trong tài liệu: qa-team@example.com. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 36 | B18 | Test JPG.jpg | JPG | Module nao co trang thai Warning? | Vector Index | Module có trạng thái Warning là Vector Index và Warning. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 37 | A18 | Test md.md | MD | RAG la viet tat cua cum tu nao? | Retrieval-Augmented Generation | RAG là viết tắt của Retrieval-Augmented Generation. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 38 | B19 | Test md.md | MD | Fallback dung khi nao? | Khi khong tim thay context phu hop de han che hallucination | Nếu tài liệu truy xuất không đủ liên quan, hệ thống nên trả fallback thay vì cố gắng trả lời. | 4 | 5 | 4 | 5 | 5 | 5 | Pass | Dung y fallback khi context khong lien quan, thieu chi tiet ve hallucination |
| 39 | A19 | Test pdf scan.pdf | PDF_SCAN | Trang 1 file scan hien thi nhan gi? | Hinh 1: Tre Viet Nam | Trang 1 file scan hiển thị nhãn "Hình 1: TreViet Nam". | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 40 | B20 | Test pdf scan.pdf | PDF_SCAN | File scan co bao nhieu trang? | 3 trang | Tài liệu có 3 trang. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 41 | A20 | Test pdf.pdf | PDF | Chuong 1 cua tai lieu PDF noi ve noi dung gi? | Tong quan ve thi giac may tinh va xu ly anh | Chương 1 nói về Tổng quan về thị giác máy tính và xử lý ảnh. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 42 | B21 | Test pdf.pdf | PDF | Bai thuc hanh chuong 1 yeu cau cai thu vien gi? | OpenCV va Pillow | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 0 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 43 | A21 | Test PNG.png | PNG | Quan mo cua khung gio nao? | 07:00 - 22:00 | Quan mô của quán cà phê May là Go Vap, TP.HCM. | 1 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 44 | B22 | Test PNG.png | PNG | Wi-Fi cua quan la gi? | MayCoffee_Free | Wi-Fi của quán là MayCoffee_Free. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 45 | A22 | Test pptx.pptx | PPTX | Tieu de slide dau la gi? | オフィス業務 | Tiêu đề slide đầu là "オフィス業務". | 5 | 5 | 5 | 5 | 5 | 5 | Pass | Dung nhung latency cao |
| 46 | B23 | Test pptx.pptx | PPTX | Bai giang khuyen nghi lam viec toi thieu bao lau o cung cong ty? | 3 nam / 最低3年間 | Bài giảng khuyến nghị làm việc tối thiểu 3 năm ở cùng công ty: 最低3年間は、同じ会社で働きましょう。. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 47 | A23 | test txt.txt | TXT | Du lich sinh thai la gi? | Du lich gan voi thien nhien, van hoa dia phuong va bao ve moi truong | Du lịch sinh thái là hình thức du lịch gắn liền với thiên nhiên, văn hóa địa phương và trách nhiệm bảo vệ môi trường. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 48 | B24 | test txt.txt | TXT | Can Gio co vai tro gi trong he sinh thai? | Khu du tru sinh quyen, bao ve bo bien, hap thu carbon | Cần Giờ có vai trò quan trọng trong việc bảo vệ bờ biển, hấp thụ carbon và duy trì đa dạng sinh học. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 49 | E02 | Test xlsx.xlsx | XLSX | Workbook Test xlsx co bao nhieu sheet va ten gi? | 3 sheet: Sheet4, Sheet2, Sheet1 | Tài liệu có 2 sheet: Sheet4, Sheet2. | 1 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 50 | B25 | Test xlsx.xlsx | XLSX | O Sheet1, thi sinh No.1 co tong diem va ket qua gi? | 34 va 合格 | Ở Sheet1, thí sinh No.1 có 総計: 34; 結果: 合格. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 51 | C01 | bao_cao_mau_chuyen_doi_so_giao_duc.pdf | PDF | Tom tat file PDF chuyen doi so giao duc trong 5 y ngan. | Tom tat dung ve chuyen doi so giao duc | Câu hỏi của bạn không rõ ràng và cụ thể, nhưng tôi sẽ cố gắng trả lời dựa trên thông tin trong tài liệu. Để chuyển đổi số trong giáo dục trong 5 năm, tài liệu đề xuất các bước s... | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 52 | C02 | file_excel_mau_song_xanh.xlsx | XLSX | Tom tat file Excel song xanh nay noi ve du lieu gi. | Chien dich song xanh trong truong hoc | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 0 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 53 | C03 | storyboard_mau_suc_khoe_hoc_duong.jpeg | JPEG | Tom tat noi dung anh storyboard suc khoe hoc duong. | 6 canh ve suc khoe hoc duong | Câu chuyện trong storyboard "Sức khỏe học đường" được chia thành 6 cảnh. Dưới đây là tóm tắt từng cảnh: - Cảnh 1: Học sinh bắt đầu ngày học - Cảnh 2: Giáo viên nhac ca và giáo d... | 5 | 5 | 5 | 5 | 2 | 5 | Pass |  |
| 54 | D01 | noi_dung_mau_thanh_pho_xanh.pdf + bao_cao_quan_ly_rac_thai_nhua.pdf | PDF | So sanh PDF Thanh pho Xanh va PDF quan ly rac thai nhua khac nhau o diem nao? | Mot file noi ve do thi xanh tong quat, mot file noi ve quan ly rac nhua khu dan cu | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 0 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |
| 55 | D02 | ke_hoach_mau_du_lich_da_lat.md + poster_mau_nang_luong_tai_tao.jpg | MD+JPG | Markdown du lich Da Lat va poster nang luong tai tao co cung chu de khong? | Khong, mot file la du lich Da Lat, mot file la nang luong tai tao | Để đi du lịch Đà Lạt và tránh nắng, bạn nên mang theo: - Áo khoác ấm. - Áo mưa mỏng hoặc dù. - Giày dễ đi bộ. - Đồ ngủ thoải mái. - Một bộ đồ đẹp để chụp ảnh. Ngoài ra, bạn cũng... | 1 | 1 | 1 | 3 | 5 | 2 | Fail | Cau hoi so sanh hai file nhung chi tra loi file Da Lat; bo qua poster nang luong tai tao |
| 56 | D03 | infographic_mau_an_toan_mang.png + bao_cao_an_toan_du_lieu_ca_nhan.docx | PNG+DOCX | Anh an toan mang va DOCX an toan du lieu ca nhan giong nhau o diem nao? | Deu lien quan bao ve thong tin/an toan so | Khi người dùng đăng ký tài khoản, mua sắm, học tập hoặc làm việc trên nền tảng số, nhiều loại dữ liệu như họ tên, số điện thoại, vị trí, lịch sử tìm kiếm và hành vi sử dụng được... | 2 | 4 | 2 | 5 | 2 | 3 | Fail | Co lay dung hai file nhung tra loi dai, tao bang/so do khong duoc yeu cau va khong neu ro diem giong nhau |
| 57 | F01 | ke_hoach_mau_du_lich_da_lat.md | MD | Tai lieu du lich Da Lat co noi ve blockchain khong? | Khong tim thay blockchain trong tai lieu | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 58 | F02 | Test pdf scan.pdf | PDF_SCAN | Co trich duoc thong tin lien he tu file scan nay khong? | Khong co email/so dien thoai ro rang | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 59 | F03 | file_excel_mau_song_xanh.xlsx | XLSX | Mat khau admin trong file Excel la gi? | Khong tim thay trong tai lieu | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 60 | F04 | Test pptx.pptx | PPTX | Bai giang nay co email lien he nao? | Khong tim thay email lien he | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 61 | G01 | ALL | MIXED | Noi dung chinh la gi? | He thong nen hoi ro tai lieu hoac tong hop khong bia | / Noi dung doc hai trong tai lieu co the co gang dieu khien mo hinh, he thong phai xem la noi dung thuong. / RQ-DOCX-01 / Test docx.docx / Ten de tai trong bao cao la gi? / Nghi... | 1 | 2 | 1 | 2 | 2 | 2 | Fail | Cau hoi mo ho nhung he thong tra noi dung ngau nhien tu RETRIEVAL_TESTING thay vi hoi ro pham vi |
| 62 | G02 | ALL | MIXED | Tom tat giup toi. | He thong nen hoi ro pham vi hoac tom tat theo workspace, khong bia | Workspace này đang có nhiều tài liệu. Bạn muốn mình xử lý tài liệu nào? Bạn có thể gọi theo số thứ tự upload hoặc tên file: - Tài liệu 1: AI Document Question Answering System.p... | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 63 | H01 | poster_mau_nang_luong_tai_tao.jpg | JPG | Poster nang luong tai tao co noi ve du lich Da Lat dung khong? | Khong, poster noi ve nang luong tai tao | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 64 | H02 | bao_cao_quan_ly_rac_thai_nhua.pdf | PDF | Bao cao rac thai nhua co noi rang tong doanh thu la 78.7M dung khong? | Khong, 78.7M thuoc anh doanh thu, khong nam trong bao cao rac thai nhua | Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác. | 5 | 5 | 5 | 5 | 5 | 5 | Pass |  |
| 65 | H03 | Test xlsx.xlsx | XLSX | Trong Test xlsx, thi sinh No.1 co tong doanh thu 78.7M phai khong? | Khong, No.1 co tong diem 34 va ket qua hop le | Ở Sheet4, thí sinh No.1 có 受験番号: KI2; 氏名: のび太 徳田; 性別: A. | 1 | 3 | 1 | 5 | 5 | 3 | Fail | Answer mismatch/fallback sai |

## 5. Loi can sua theo muc do

### Critical
- D02 / ke_hoach_mau_du_lich_da_lat.md + poster_mau_nang_luong_tai_tao.jpg: Cau hoi so sanh hai file nhung chi tra loi file Da Lat; bo qua poster nang luong tai tao. Cau hoi: Markdown du lich Da Lat va poster nang luong tai tao co cung chu de khong?. Actual: Để đi du lịch Đà Lạt và tránh nắng, bạn nên mang theo: - Áo khoác ấm. - Áo mưa mỏng hoặc dù. - Giày dễ đi bộ. - Đồ ngủ thoải mái. - Một bộ đồ đẹp để chụp ảnh. Ngoài ra, bạn cũng nên kiểm tra thời tiết trước khi đi và ...
- G01 / ALL: Cau hoi mo ho nhung he thong tra noi dung ngau nhien tu RETRIEVAL_TESTING thay vi hoi ro pham vi. Cau hoi: Noi dung chinh la gi?. Actual: | Noi dung doc hai trong tai lieu co the co gang dieu khien mo hinh, he thong phai xem la noi dung thuong. | RQ-DOCX-01 | Test docx.docx | Ten de tai trong bao cao la gi? | Nghien cuu, ung dung mo hinh AI ket hop do t...
- A01 / AI Document Question Answering System.pptx: Answer mismatch/fallback sai. Cau hoi: De tai trong slide dau la gi?. Actual: De tai trong slide đầu là Luồng hỏi đáp AI/RAG.
- A15 / Test docx.docx: Answer mismatch/fallback sai. Cau hoi: De tai nghien cuu trong bao cao la gi?. Actual: Dự án không chỉ đạt được các cột mốc về mặt kỹ thuật mà còn chứng minh được tính thực tiễn cao trong việc hỗ trợ tiếp cận pháp luật số. Thay vì chỉ tìm kiếm theo từ khóa đơn thuần, hệ thống định vị các "điểm neo" tri ...
- E01 / file_excel_mau_song_xanh.xlsx: Answer mismatch/fallback sai. Cau hoi: File Excel song xanh co nhung sheet nao?. Actual: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
- E02 / Test xlsx.xlsx: Answer mismatch/fallback sai. Cau hoi: Workbook Test xlsx co bao nhieu sheet va ten gi?. Actual: Tài liệu có 2 sheet: Sheet4, Sheet2.
- B07 / file_excel_mau_song_xanh.xlsx: Answer mismatch/fallback sai. Cau hoi: Ngay 2026-05-01 co hoat dong gi va o khu vuc nao?. Actual: Ở Du_lieu_chien_dich, dòng 3, Khu vực: Ký túc xá.
- H03 / Test xlsx.xlsx: Answer mismatch/fallback sai. Cau hoi: Trong Test xlsx, thi sinh No.1 co tong doanh thu 78.7M phai khong?. Actual: Ở Sheet4, thí sinh No.1 có 受験番号: KI2; 氏名: のび太 徳田; 性別: A.

### High
- A02 / bai_trinh_chieu_mau_thu_vien_thong_minh.pptx: Answer mismatch/fallback sai. Cau hoi: Bai trinh chieu mau noi ve chu de gi?. Actual: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
- A03 / bao_cao_an_toan_du_lieu_ca_nhan.docx: Answer mismatch/fallback sai. Cau hoi: Tai lieu DOCX nay noi ve van de gi?. Actual: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
- B11 / noi_dung_mau_thanh_pho_xanh.pdf: Answer mismatch/fallback sai. Cau hoi: Bang so lieu mau trong PDF Thanh pho Xanh co nhung chi so nao?. Actual: bản, bảng và bố cục cơ bản trong một file PDF.
- B13 / poster_mau_nang_luong_tai_tao.jpg: Answer mismatch/fallback sai. Cau hoi: Poster neu nhung loai nang luong nao?. Actual: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
- B21 / Test pdf.pdf: Answer mismatch/fallback sai. Cau hoi: Bai thuc hanh chuong 1 yeu cau cai thu vien gi?. Actual: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
- C02 / file_excel_mau_song_xanh.xlsx: Answer mismatch/fallback sai. Cau hoi: Tom tat file Excel song xanh nay noi ve du lieu gi.. Actual: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
- D01 / noi_dung_mau_thanh_pho_xanh.pdf + bao_cao_quan_ly_rac_thai_nhua.pdf: Answer mismatch/fallback sai. Cau hoi: So sanh PDF Thanh pho Xanh va PDF quan ly rac thai nhua khac nhau o diem nao?. Actual: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
- D03 / infographic_mau_an_toan_mang.png + bao_cao_an_toan_du_lieu_ca_nhan.docx: Co lay dung hai file nhung tra loi dai, tao bang/so do khong duoc yeu cau va khong neu ro diem giong nhau. Cau hoi: Anh an toan mang va DOCX an toan du lieu ca nhan giong nhau o diem nao?. Actual: Khi người dùng đăng ký tài khoản, mua sắm, học tập hoặc làm việc trên nền tảng số, nhiều loại dữ liệu như họ tên, số điện thoại, vị trí, lịch sử tìm kiếm và hành vi sử dụng được thu thập. ### Bảng tổng hợp | Chủ đề | ...

### Medium
- A06 / content_summary.md: Tra loi khong dung trong tam file content_summary; truy xuat dung file nhung sai noi dung can hoi. Cau hoi: File content_summary.md mo ta noi dung gi?. Actual: 3.3.1. - Độ chính xác và Khả năng kiểm soát ảo giác (Accuracy & Grounding) - Trong pha Offline, hệ thống thực hiện xử lý dữ liệu nguồn từ các văn bản pháp luật (DOCX), trích xuất metadata và áp dụng kỹ thuật phân mảnh...
- B06 / content_summary.md: Answer mismatch/fallback sai. Cau hoi: content_summary.md ghi tong so paragraph la bao nhieu?. Actual: Chatbot trí tuệ nhân tạo là một bước tiến vượt bậc so với các chương trình trả lời tự động truyền thống, nhờ khả năng hiểu và xử lý ngôn ngữ tự nhiên để tương tác với con người một cách linh hoạt. - Về - Dùng để phân ...
- A11 / pdf_page_index.md: Answer mismatch/fallback sai. Cau hoi: pdf_page_index.md dung de lam gi?. Actual: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
- B12 / pdf_page_index.md: Answer mismatch/fallback sai. Cau hoi: Trang dau trong pdf_page_index.md nhac toi noi dung gi?. Actual: Tôi không tìm thấy đủ thông tin trong tài liệu để trả lời chính xác.
- B14 / RETRIEVAL_TESTING_QUESTION_SET.md: Answer mismatch/fallback sai. Cau hoi: Bo test nay liet ke nhung file anh nao?. Actual: Bo test nay duoc xay dung truc tiep tu bo file trong thu muc: | RQ-PDFSCAN-02 | Test pdf scan.pdf | Co trich duoc email hoac so dien thoai tu file scan nay khong? | RQ-PPTX-04 | Test pptx.pptx | Slide nao noi ve thoi ...
- A21 / Test PNG.png: Answer mismatch/fallback sai. Cau hoi: Quan mo cua khung gio nao?. Actual: Quan mô của quán cà phê May là Go Vap, TP.HCM.

### Low
- Mot so cau tra loi dung nhung van phong con dai dong: lap lai cau hoi, mo dau bang ?Cau hoi cua ban...?, hoac them bang/so do khi khong duoc yeu cau.
- Mot so cau dung nhung latency cao 30-55s, dac biet voi PPTX/PDF/MD tong quan.

## 6. Phan tich theo loai file

- PDF: doc text tot voi cau hoi truc tiep, nhung bang PDF va so lieu trong bang chua on; cross-PDF compare fail.
- DOCX: chi tiet nhu giang vien/sinh vien tot, nhung cau hoi chu de/de tai co the lay nham chunk giua tai lieu.
- MD/TXT: TXT tot; MD dai hoac file chi muc/content_summary bi truy xuat kem voi cau hoi tong quan/so lieu metadata.
- Excel/XLSX: ingestion giu sheet/header/formula, nhung QA sheet count, row lookup theo ngay, summary va false-premise deu yeu. Day la loai kem nhat.
- PPTX: cau hoi chi tiet co luc tot, nhung slide title/chuyen de voi file PPTX shapes phuc tap co the fallback/lay sai slide.
- PNG/JPG/JPEG: OCR text-on-image co the tra dung cau don gian; anh moi co nhieu loi OCR tieng Viet khong dau/sai ky tu. Poster nang luong fail khi hoi danh sach loai nang luong.

## 7. De xuat cai thien

- File parsing: them document-level summary/index sau ingest cho moi file, gom title, headings, pages/slides/sheets, bang va OCR text chinh.
- OCR/Vision: hau xu ly OCR tieng Viet bang spell correction nhe, bo ky tu nhieu, tach cac block theo layout cua poster/infographic/storyboard.
- Chunking: voi PDF/PPTX/DOCX them chunk dau tai lieu co title/metadata vao priority context; voi PDF table tao markdown table/chunk rieng.
- Metadata: gan content_type ro cho MD/TXT; luu workbook_sheet_count, slide_count, page_count, image_ocr_confidence.
- Retrieval: voi cau hoi tong quan/dem/sheet/slide/page, dung deterministic metadata/index thay vi top-k semantic thuan.
- Reranking: khi multi-document compare, enforce coverage moi file it nhat 1-2 chunk truoc khi rerank.
- Prompt/answer: cau ro rang thi tra ngan; khong them bang/so do neu user khong yeu cau; bo prefix ?Cau hoi cua ban...?.
- Fallback: false-premise checker cho cau hoi ?co dung khong/phai khong?, nhat la voi bang Excel.
- Citation: kiem tra answer span voi source chunk; neu answer tu file A thi khong citation file B va nguoc lai.
- Auto evaluation: duy tri bo test nay thanh regression suite, luu expected terms + expected source + latency threshold.