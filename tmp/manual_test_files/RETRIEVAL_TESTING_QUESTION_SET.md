# RETRIEVAL TESTING - BO CAU HOI KIEM THU THUC TE

## 1) Pham vi bo test
Bo test nay duoc xay dung truc tiep tu bo file trong thu muc:
- Test md.md
- Test docx.docx
- Test xlsx.xlsx
- Test pptx.pptx
- Test pdf.pdf
- Test pdf scan.pdf
- test txt.txt
- Test JPG.jpg
- Test PNG.png
- Test jpeg.jpeg

Muc tieu:
- Kiem tra retrieval theo nguon (dung file)
- Kiem tra retrieval theo noi dung (dung fact/chu de)
- Kiem tra retrieval da ngon ngu (Viet - Anh - Nhat)
- Kiem tra fallback khi tai lieu khong co thong tin

## 2) Cach chay va cham
Voi moi cau hoi:
1. Dat cau hoi trong he thong.
2. Ghi lai Top-1 source va Top-3 source (neu he thong co hien thi).
3. Doi chieu voi cot Nguon ky vong va Tu khoa neo.
4. Xac dinh vi tri context dung trong Top-3:
- rank_i = 1 neu context dung o Top-1.
- rank_i = 2/3 neu context dung o vi tri 2/3.
- rank_i = 0 neu khong co context dung trong Top-3.
5. Danh dau ket qua:
- Pass: Top-1 dung nguon hoac trong Top-3 co nguon dung, va context phu hop.
- Partial: Dung y nhung sai nguon.
- Fail: Sai y hoac khong co context lien quan.

## 3) Bang Retrieval Testing + Bo cau hoi

| ID | Nguon ky vong | Cau hoi kiem thu | Dap an tham chieu ngan | Tu khoa neo de doi chieu |
|---|---|---|---|---|
| RQ-MD-01 | Test md.md | RAG la viet tat cua cum tu nao? | Retrieval-Augmented Generation. | RAG, Retrieval-Augmented Generation |
| RQ-MD-02 | Test md.md | Vi sao can fallback trong AI Document Chat? | De tranh hallucination khi khong du context. | fallback, hallucination, khong tim thay thong tin |
| RQ-MD-03 | Test md.md | Top-k Retrieval la gi? | Lay k chunk co diem tuong dong cao nhat voi cau hoi. | Top-k, k chunk, tuong dong cao nhat |
| RQ-MD-04 | Test md.md | He thong neu ten cac nhom kiem thu chinh nao? | Functional, Processing, Retrieval, Answer Quality, Fallback, Security, Performance, Usability. | Nhom kiem thu, Functional Testing, Retrieval Testing |
| RQ-MD-05 | Test md.md | FAISS duoc nhac den trong boi canh nao? | La lua chon pho bien cho he thong local/do an vi nhe, nhanh, de tich hop. | FAISS, local, nhe, nhanh |
| RQ-MD-06 | Test md.md | Metadata quan trong vi sao trong retrieval? | Giup xac dinh file/trang/slide/section, hien thi citation, dung pham vi workspace. | Metadata, citation, workspace |
| RQ-MD-07 | Test md.md | Prompt injection trong tai lieu la gi? | Noi dung doc hai trong tai lieu co the co gang dieu khien mo hinh, he thong phai xem la noi dung thuong. | Ignore previous instructions, prompt injection |
| RQ-MD-08 | Test md.md | Huong phat trien nao duoc de xuat cho he thong? | Tich hop reranker, cai thien vision, citation chi tiet, toi uu toc do, dashboard, bao mat. | huong phat trien, reranker, citation |

| RQ-DOCX-01 | Test docx.docx | Ten de tai trong bao cao la gi? | Nghien cuu, ung dung mo hinh AI ket hop do thi tri thuc ho tro tra cuu chinh xac luat CNTT. | De tai, do thi tri thuc, luat cong nghe thong tin |
| RQ-DOCX-02 | Test docx.docx | Giang vien huong dan la ai? | Nguyen Van Huy. | Giang vien huong dan, Nguyen Van Huy |
| RQ-DOCX-03 | Test docx.docx | Sinh vien thuc hien la ai? | Huynh Ba Thanh. | Sinh vien thuc hien, Huynh Ba Thanh |
| RQ-DOCX-04 | Test docx.docx | Bao cao neu kien truc retrieval nao noi bat? | Hybrid GraphRAG ket hop Qdrant va Neo4j. | Hybrid GraphRAG, Qdrant, Neo4j |
| RQ-DOCX-05 | Test docx.docx | Tu khoa nghien cuu trong bao cao gom nhung gi? | RAG, GraphRAG, Knowledge Graph, PhoBERT, Qdrant, Neo4j... | Tu khoa, PhoBERT, Vietnamese Legal NLP |
| RQ-DOCX-06 | Test docx.docx | Chi so hieu nang nao duoc neu cho kien truc Hybrid? | Hit@5 ~94.00% va Recall ~0.9400. | Hit@5, 94.00, Recall 0.9400 |
| RQ-DOCX-07 | Test docx.docx | He thong trong bao cao con han che van hanh nao? | Chua ho tro streaming, nguoi dung phai cho Gemini xong toan bo. | Chua ho tro Streaming, Gemini |

| RQ-XLSX-01 | Test xlsx.xlsx | Workbook co bao nhieu sheet va ten gi? | 3 sheet: Sheet1, Sheet2, Sheet4. | Sheet1, Sheet2, Sheet4 |
| RQ-XLSX-02 | Test xlsx.xlsx | O Sheet1, thi sinh No.1 co tong diem va ket qua gi? | Tong 34, ket qua Hop cach/Dat (hien thi la hop le: 合格). | No. 1, 34, 合格 |
| RQ-XLSX-03 | Test xlsx.xlsx | O Sheet1, ai co tong diem cao nhat trong cac dong mau? | Yamashita Keiko (山下 恵子), tong 36.5. | 36.5, 山下 恵子 |
| RQ-XLSX-04 | Test xlsx.xlsx | O Sheet1, ket qua cua thi sinh KE1 la gi? | Khong dat (不合格), tong 18. | KE1, 18, 不合格 |
| RQ-XLSX-05 | Test xlsx.xlsx | O Sheet4, ghi chu cong thuc tong diem cho Nhat ngu/Giao duc la gi? | (Nhat ngu*2) + Toan + Van. | 注, 日本語学科と教育学科, 日本語*2 |
| RQ-XLSX-06 | Test xlsx.xlsx | O Sheet4, ghi chu cong thuc cho Quan tri kinh doanh la gi? | Nhat ngu + Toan + Van. | 経営学科, 日本語＋数学＋文学 |
| RQ-XLSX-07 | Test xlsx.xlsx | Cac cot diem chinh trong bang la gi? | Nhat ngu, Toan, Van, Tong, Ket qua. | 日本語, 数学, 文学, 総計, 結果 |

| RQ-PPTX-01 | Test pptx.pptx | Tieu de chu de slide dau la gi? | オフィス業務. | オフィス業務 |
| RQ-PPTX-02 | Test pptx.pptx | Bai giang nhan manh quy tac giao tiep nao? | Ho-ren-so, quy tac chao hoi va tu gioi thieu. | あいさつのルール, ほう・れん・そう |
| RQ-PPTX-03 | Test pptx.pptx | Muc tieu mon hoc la gi? | Hieu va thuc hanh business manner cua Nhat. | 授業の目的, ビジネスマナー |
| RQ-PPTX-04 | Test pptx.pptx | Slide nao noi ve thoi gian gan bo cong ty? | Khuyen nghi toi thieu 3 nam o cung cong ty. | 最低3年間, 同じ会社で働きましょう |
| RQ-PPTX-05 | Test pptx.pptx | Quan diem ve tien va y nghia cong viec duoc neu the nao? | Voi nguoi Nhat, y nghia cong viec (yarigai) duoc de cao hon tien. | お金 < やりがい |
| RQ-PPTX-06 | Test pptx.pptx | Thong diep ket thuc ve khac biet van hoa la gi? | Nhat va Viet khac nhau ve van hoa/thoi quen/cach nghi, can hieu de hanh dong phu hop. | 文化・習慣・考え方が違うだけ |

| RQ-PDF-01 | Test pdf.pdf | Chuong 1 cua tai lieu PDF noi ve chu de gi? | Tong quan ve thi giac may tinh va xu ly anh. | Chương 1, thị giác máy tính, xử lý ảnh |
| RQ-PDF-02 | Test pdf.pdf | Tai lieu dinh nghia linh vuc nao la lien quan chat che? | Computer Vision va Image Processing. | Computer Vision, Image processing |
| RQ-PDF-03 | Test pdf.pdf | Tai lieu co muc lich su phat trien cua linh vuc nao? | Lich su phat trien Thi giac may tinh. | Lịch sử phát triển, Computer Vision |
| RQ-PDF-04 | Test pdf.pdf | Co phan noi ve uu diem va nhuoc diem cua gi? | Cua Thi giac may tinh. | Ưu điểm và nhược điểm |
| RQ-PDF-05 | Test pdf.pdf | Tai lieu co noi ve xu huong tuong lai nao? | Xu huong va su phat trien tuong lai cua Thi giac may tinh. | Xu hướng, phát triển tương lai |
| RQ-PDF-06 | Test pdf.pdf | Bai thuc hanh chuong 1 yeu cau cai thu vien gi? | OpenCV va Pillow. | Bài thực hành chương 1, OpenCV, Pillow |
| RQ-PDF-07 | Test pdf.pdf | Trang cuoi cua tai lieu la muc gi? | Q & A. | Q & A |

| RQ-TXT-01 | test txt.txt | Du lich sinh thai la gi? | Hinh thuc du lich gan voi thien nhien, van hoa dia phuong va trach nhiem bao ve moi truong. | du lich sinh thai, thien nhien, bao ve moi truong |
| RQ-TXT-02 | test txt.txt | Can Gio co vai tro gi trong he sinh thai? | Khu du tru sinh quyen, bao ve bo bien, hap thu carbon, duy tri da dang sinh hoc. | Can Gio, du tru sinh quyen, hap thu carbon |
| RQ-TXT-03 | test txt.txt | Trang An noi bat voi loai hinh du lich nao? | He thong nui da voi, hang dong, song nuoc; hoat dong du thuyen tham quan. | Trang An, hang dong, du thuyen |
| RQ-TXT-04 | test txt.txt | Nguyen tac phat trien du lich sinh thai ben vung gom gi? | Gioi han khach, bao ton moi truong song, vat lieu than thien, giao duc y thuc, danh gia tac dong dinh ky. | nguyen tac ben vung, gioi han so luong khach |
| RQ-TXT-05 | test txt.txt | Cong nghe co the ho tro du lich sinh thai nhu the nao? | Ban do so, dat ve truc tuyen, camera/cam bien moi truong, AI du doan luong khach va rui ro. | ban do so, dat ve truc tuyen, AI |
| RQ-TXT-06 | test txt.txt | Cac thach thuc khi phat trien du lich sinh thai la gi? | Qua tai khach, ha tang han che, thuong mai hoa qua muc, y thuc du khach chua cao. | thach thuc, luong khach qua dong, thuong mai hoa |
| RQ-TXT-07 | test txt.txt | Dia diem nao phu hop de tham quan rung ngap man? | Rung ngap man Can Gio. | rung ngap man, Can Gio |

| RQ-IMG-OCR-01 | Test JPG.jpg | Email lien he trong trang OCR test la gi? | qa-team@example.com | Email, qa-team@example.com |
| RQ-IMG-OCR-02 | Test JPG.jpg | So dien thoai lien he la gi? | 028 3876 1234 | Phone, 028 3876 1234 |
| RQ-IMG-OCR-03 | Test JPG.jpg | Module nao dang o trang thai Warning? | Vector Index. | Vector Index, Warning |
| RQ-IMG-OCR-04 | Test JPG.jpg | Ngay ghi tren tai lieu OCR test la ngay nao? | 14/05/2026 | Date, 14/05/2026 |
| RQ-IMG-OCR-05 | Test JPG.jpg | Workspace tren tai lieu OCR test la gi? | Demo-Test-01 | Workspace, Demo-Test-01 |

| RQ-IMG-CAFE-01 | Test PNG.png | Quan co ten gi? | QUAN CA PHE MAY. | QUÁN CÀ PHÊ MÂY |
| RQ-IMG-CAFE-02 | Test PNG.png | Quan mo cua khung gio nao? | 07:00 - 22:00. | OPEN 07:00 - 22:00 |
| RQ-IMG-CAFE-03 | Test PNG.png | Ten Wi-Fi la gi? | MayCoffee_Free. | Wi-Fi, MayCoffee_Free |
| RQ-IMG-CAFE-04 | Test PNG.png | Quan dang co khuyen mai gi? | Giam 20% cho sinh vien. | Khuyến mãi 20% cho sinh viên |
| RQ-IMG-CAFE-05 | Test PNG.png | Gia Latte la bao nhieu? | 45.000d. | Latte 45.000đ |

| RQ-IMG-SALES-01 | Test jpeg.jpeg | Doanh thu tuan nao cao nhat? | Tuan 4, gia tri 22 trieu dong. | Tuần 4, 22 |
| RQ-IMG-SALES-02 | Test jpeg.jpeg | Tong so don hang la bao nhieu? | 260. | Tổng đơn hàng: 260 |
| RQ-IMG-SALES-03 | Test jpeg.jpeg | Tong doanh thu la bao nhieu? | 78.7M. | Tổng doanh thu: 78.7M |
| RQ-IMG-SALES-04 | Test jpeg.jpeg | Kenh Online co bao nhieu don va doanh thu bao nhieu? | 120 don, 36.5M. | Online, 120, 36.5M |
| RQ-IMG-SALES-05 | Test jpeg.jpeg | Bao cao thuoc thang nao? | Thang 05/2026. | 05/2026, Monthly Sales Summary |

| RQ-PDFSCAN-01 | Test pdf scan.pdf | Tai lieu scan co noi dung text ro rang nao ngoai "Hinh 1/2/3" khong? | Khong co thong tin text dang ke, can OCR/vision sau hon. | Hình 1, Hình 2, Hình 3 |
| RQ-PDFSCAN-02 | Test pdf scan.pdf | Co trich duoc email hoac so dien thoai tu file scan nay khong? | Khong thay trong noi dung trich xuat hien tai. | Total chars rat thap, scan |
| RQ-PDFSCAN-03 | Test pdf scan.pdf | Trang nao chua noi dung chi tiet nhat? | Khong trang nao ro, ca 3 trang gan nhu chi co nhan Hinh. | Hình 1/2/3 |

## 4) Nhom cau hoi fallback (ngoai pham vi) de test chong hallucination

| ID | Cau hoi | Ky vong |
|---|---|---|
| FB-01 | So CCCD cua sinh vien trong Test docx.docx la gi? | Fallback: tai lieu khong co thong tin nay. |
| FB-02 | Test pdf.pdf co nhac den mo hinh YOLOv8 chi tiet o trang nao? | Neu khong co bang chung trong context, phai fallback/co dieu kien. |
| FB-03 | Quan ca phe trong Test PNG.png co website gi? | Fallback: khong co website trong noi dung anh. |
| FB-04 | Trong Test xlsx.xlsx co thong tin dia chi nha rieng cua thi sinh khong? | Fallback: khong co thong tin nay. |
| FB-05 | Tai lieu nao co ma so thue doanh nghiep? | Fallback neu khong tim thay trong nguon. |

## 5) Mau ghi ket qua (chuan theo cong thuc Top-1 / Top-3 / MRR)

| ID | Top-1 Source Thuc Te | Top-3 Sources Thuc Te | rank_i (0/1/2/3) | Top1_Hit | Top3_Hit | RR_i = 1/rank_i | Answer dung y? (Y/N) | Ket qua |
|---|---|---|---:|---:|---:|---:|---|---|
| RQ-... |  |  |  |  |  |  |  |  |

Quy tac dien cot:
- Top1_Hit = 1 neu rank_i = 1, nguoc lai = 0.
- Top3_Hit = 1 neu rank_i > 0, nguoc lai = 0.
- RR_i = 1/rank_i neu rank_i > 0, neu rank_i = 0 thi RR_i = 0.

Cong thuc danh gia tong hop:
- Top-1 Accuracy = (tong Top1_Hit) / N
- Top-3 Accuracy = (tong Top3_Hit) / N
- MRR = (tong RR_i) / N

Mau cong thuc Excel (gia su hang dau tien la dong 2, rank_i o cot D):
- E2 (Top1_Hit): =IF(D2=1,1,0)
- F2 (Top3_Hit): =IF(D2>0,1,0)
- G2 (RR_i): =IF(D2>0,1/D2,0)
- Top-1 Accuracy: =SUM(E:E)/COUNTA(A:A)
- Top-3 Accuracy: =SUM(F:F)/COUNTA(A:A)
- MRR: =SUM(G:G)/COUNTA(A:A)
