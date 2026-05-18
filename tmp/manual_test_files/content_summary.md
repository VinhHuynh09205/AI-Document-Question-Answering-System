# Test JPG.jpg (JPG)
Dimensions: 1086x1448, Mode: RGB

---

# Test PNG.png (PNG)
Dimensions: 1448x1086, Mode: RGB

---

# Test docx.docx (DOCX)
Total paragraphs: 346
- BỘ GIAO THÔNG VẬN TẢI TRƯỜNG ĐẠI HỌC VẬN TẢI THÀNH PHỐ HỒ CHÍ MINH VIỆN CÔNG NGHỆ THÔNG TIN VÀ ĐIỆN, ĐIỆN TỬ
- BÁO CÁO THỰC TẬP TỐT NGHIỆP
- Đề tài: Nghiên cứu, ứng dụng mô hình AI, kết hợp đồ thị tri thức hỗ trợ tra cứu chính xác luật công nghệ thông tin
- Chuyên ngành: Công nghệ thông tin
- Giảng viên hướng dẫn: Nguyễn Văn Huy
- Sinh viên thực hiện: Huỳnh Bá Thành
- MSSV:084205002647
	           			Lớp: CN2303D
- Thành phố Hồ Chí Minh, ngày 25 tháng 04 năm 2026
- TÓM TẮT
- Đề tài xây dựng một trợ lý hội thoại tư vấn pháp luật Công nghệ thông tin (CNTT) tại Việt Nam dựa trên:. Kiến trúc Hybrid GraphRAG — kết hợp truy xuất vector (Qdrant) với truy hồi đồ thị tri thức (Neo
- Từ khóa: RAG, GraphRAG, Knowledge Graph, PhoBERT, Qdrant, Neo4j, Vietnamese Legal NLP, Hierarchical Chunking, Multi-Query Retrieval.
- LỜI NÓI ĐẦU
- Trong bối cảnh chuyển đổi số mạnh mẽ tại Việt Nam, lĩnh vực Công nghệ thông tin ngày càng gắn bó chặt chẽ với khung pháp lý quốc gia: từ Luật An ninh mạng, Luật Công nghệ thông tin, Luật Sở hữu trí tu
- Truy xuất chính xác Điều / Khoản / Điểm trong các văn bản pháp luật CNTT còn hiệu lực;
- Trình bày được mối liên hệ giữa các văn bản (Luật — Nghị định — Thông tư) thông qua đồ thị tri thức;
- Sinh đáp án có trích dẫn rõ ràng, hạn chế tối đa hiện tượng “ảo giác” (hallucination) thường gặp ở các mô hình ngôn ngữ lớn.
- Đề tài tích hợp ba thành phần cốt lõi. Vector store Qdrant cho tìm kiếm ngữ nghĩa với mô hình nhúng DEk21_hcmute_embedding (huyydangg/DEk21_hcmute_embedding) một mô hình dựa trên kiến trúc RoBERTa đượ
- LỜI CẢM ƠN
- Em xin chân thành cảm ơn thầy Nguyễn Văn Huy, giảng viên hướng dẫn đã tận tình chỉ bảo trong suốt quá trình thực hiện. Không chỉ hiểu rõ hơn về các kiến thức nền tảng và ứng dụng thực tế mà còn học hỏ
- Do kỹ năng và kiến thức còn hạn chế, báo cáo không tránh khỏi thiếu sót; em rất mong nhận được sự góp ý của Quý Thầy/Cô để hoàn thiện hơn.
- Em xin chân thành cảm ơn!
- Sinh viên thực hiện
- Huỳnh Bá Thành
- NHẬN XÉT CỦA GIẢNG VIÊN
- …………………………………………………………………………………………………………………………………………………………………………………………………………………………………….…………………………………………………………………………………………………………………………………………………………………………………………………………………………………….……………………………………………………………………
- CHƯƠNG 1: TỔNG QUAN ĐỀ TÀI
- Chatbot trí tuệ nhân tạo là một bước tiến vượt bậc so với các chương trình trả lời tự động truyền thống, nhờ khả năng hiểu và xử lý ngôn ngữ tự nhiên để tương tác với con người một cách linh hoạt. Về 
- Dùng để phân loại các Nút thành các nhóm chung để dễ dàng quản lý và tăng tốc độ truy vấn.
- Với Graph Traversal, hệ thống tự động thực hiện bước nhảy từ nút Luật qua quan hệ [:CO_NGHI_DINH_HUONG_DAN] để truy xuất chính xác các chế tài nằm ở văn bản khác.
- Trong kiến trúc RAG, Qdrant đóng vai trò là kho lưu trữ vector mật độ cao (Dense Vector), cho phép thực hiện tìm kiếm ngữ nghĩa với tốc độ cực nhanh trên tập dữ liệu lớn. Việc lựa chọn Qdrant thay vì 
- Phân tích chức năng cho thấy hệ thống phải vượt qua giới hạn của tìm kiếm truyền thống để đạt tới khả năng Suy luận đa chặng (Multi-hop Reasoning). Điều này đòi hỏi một cơ chế điều phối dữ liệu chặt c
- 3.3.1. Độ chính xác và Khả năng kiểm soát ảo giác (Accuracy & Grounding)
- Trong pha Offline, hệ thống thực hiện xử lý dữ liệu nguồn từ các văn bản pháp luật (DOCX), trích xuất metadata và áp dụng kỹ thuật phân mảnh dữ liệu 4 tầng (4-tier chunking) để xây dựng cấu trúc phân 
- "chuong_so": "1", "chuong_ten": "Quy định chung",
- TEXT INDEX entity_name_idx FOR (n:Entity) ON n.name
- 3.7.4. Tổng hợp và Phản hồi có Căn cứ
- Để đảm bảo mô hình không chỉ phản hồi đúng mà còn chuyên nghiệp và chặt chẽ, hệ thống áp dụng chiến lược thiết kế câu lệnh kết hợp giữa hai phương pháp tối ưu:
- Để giải quyết triệt để sự khác biệt giữa các môi trường phát triển và thực tế, hệ thống được đóng gói toàn diện bằng công nghệ Docker, đảm bảo tính đồng nhất và khả năng vận hành ổn định trên mọi hạ t
- Kiến trúc Hybrid (GraphRAG): Đây là phương pháp tối ưu nhất, đạt Hit@5 lên đến 94.00% và Recall 0.9400. Sự kết hợp giữa sức mạnh tìm kiếm ngữ nghĩa của Qdrant và tư duy mạng lưới của Neo4j đã tạo ra m
- Về mặt kỹ thuật vận hành, hệ thống còn một số rào cản về trải nghiệm. Chưa hỗ trợ Streaming: Người dùng hiện phải chờ mô hình Gemini hoàn thành toàn bộ quá trình suy luận và sinh văn bản trước khi nhậ

---

# Test jpeg.jpeg (JPEG)
Dimensions: 1086x1448, Mode: RGB

---

# Test md.md (MD)

---

# Test pdf scan.pdf (PDF)
Page count: 3
### Page 1
- Hình 1:
### Page 2
- Hình 2:
### Page 3
- Hình 3:
Total characters: 49

---

# Test pdf.pdf (PDF)
Page count: 19
### Page 1
- Chương 1:
- Tổng quan về thị giác máy tính và xử lý ảnh
### Page 2
- Thị giác Máy tính và Xử lý Ảnh là gì?
- 2
### Page 3
- Lịch sử phát triển của Thị giác Máy tính (Computer Vision)
- 3
### Page 4
- Các ứng dụng thực tế của Thị giác máy tính
- Thị giác máy tính (Computer Vision) đã và đang trở thành một công nghệ cốt
### Page 5
- Ưu điểm và nhược điểm của Thị giác máy tính
- Ưu điểm
### Page 6
- Xu hướng và Sự Phát triển Tương Lai của Thị giác Máy tính
- Thị giác máy tính đang trải qua một giai đoạn phát triển mạnh mẽ và hứa hẹn sẽ còn
### Page 7
- Các khái niệm cơ bản về ảnh
- Ảnh là một đại diện trực quan của một đối tượng hoặc một cảnh vật, được tạo ra
### Page 8
- Các khái niệm cơ bản về ảnh
- Các không gian màu. Không gian màu chính là mô hình toán học dùng để mô tả
### Page 9
- Các ví dụ về ảnh số
### Page 10
- Xử lý ảnh
- Xử lý ảnh là các thuật toán thay đổi hình ảnh đầu vào để tạo
Total characters: 21989

---

# Test pptx.pptx (PPTX)
## オフィス業務
- オフィス業務
- 担当講師
- 正忠　武
## 主な授業内容
- 主な授業内容
- 仕事をする意味
- 職場での１日
- あいさつのルールと自己紹介の仕方
- 仕事の基本　～ほう・れん・そう～
## Slide 3
- 先生も頑張ります！
- 一緒に頑張って
- 勉強しましょう！
## Slide 4
- 分からないことを
- そのままにしないで
- 必ず質問しましょう！
## ＜授業の目的＞
- ＜授業の目的＞
## 企業実習評価表のコメント
- 企業実習評価表のコメント
- 日本とベトナムには、様々な文化や習慣の違いがあります。それを理解できないことが、ビジネスにおけるクレームにつながります。
- よって、日本の会社で働くためには、日本人レベルのビジネスマナーを習得することが必要だと思います。
## Slide 7
- ①　“それ”は何のことですか？
- ②　この学生を
- どう評価していますか？
## ＜授業の目的＞
- ＜授業の目的＞
- 日本のビジネスマナーを理解し実践できるようにすること
## Slide 9
- 覚えるだけ
## Slide 10
- 覚えるだけ
## Slide 11
- 勉強したこと
- 覚えたことを
- 実践して下さい！！！
## Slide 12
- 実践しなければ
- どれだけ勉強しても
- 知らないのと同じです！
## 日本人は、どんな人と一緒に仕事がしたいと考えていると思いますか？
- 日本人は、どんな人と一緒に仕事がしたいと考えていると思いますか？
## 日本人は、どんな人と一緒に仕事がしたいと考えていますか？
- 日本の文化・習慣
- ビジネスマナーを
- 理解している人
- 素直な人
- 日本人は、どんな人と一緒に仕事がしたいと考えていますか？
## 仕事をする意味
- 仕事をする意味
- どうして働くのか？
- 何のために仕事をするのか？
## Slide 16
- ベトナム人の皆さんは
- どう考えていますか？
- どうして働くのか？
- 何のために仕事をするのか？
## 仕事をする意味
- 仕事をする意味
- ～４つの視点～
- 仕事
## “やりがい”
- “やりがい”
## “やりがい”とは？
- “やりがい”とは？
- <大辞泉>
- そのことをするだけの価値と、それにともなう気持ちの張り。やり甲斐。
- <はてなキーワード>
- 仕事をするに当たっての張り合い。
## 仕事をする意味
- 仕事をする意味
- ～４つの視点～
- 仕事
## Slide 21
- 「どうしてこの会社で
- 働きたいですか？」
- と聞かれたら
- この３つの視点から考えて
- どうやりがいを感じているか
## 日本人にとっては・・・
- 日本人にとっては・・・
- お金
- ＜
- やりがい
## 会社を辞めたいと思ったら？
- 会社を辞めたいと思ったら？
- 他に条件のいい会社があったら？
## 多くの会社で働いた経験がある
- 多くの会社で働いた経験がある
- ↓
- 日本人にとって、
- どちらの方が評価が高いですか？
- １つの会社で長く働いている
## 最低３年間は、同じ会社で働きましょう！
- 最低３年間は、同じ会社で働きましょう！
- 相手の立場に立って考えると
- 自分がどうするべきか
- 自然に分かります！
## Slide 26
- 考えてみましょう！
## Slide 27
- 本屋さんのアルバイト
## Slide 28
- １０人が面接を受けて、
- 合格したのは１人だけでした。
- どうして、この１人は
- 合格できたと思いますか？
## Slide 29
- 本屋さんのアルバイト
## Slide 30
- 「お給料はいくらですか？」
- と聞かなかったからです！
## 日本人にとっては・・・
- 日本人にとっては・・・
- お金
- ＜
- やりがい
## Slide 32
## Slide 33
- もちろんお金は必要ですが
- 「お金！」「お金！」と
- はっきり言われると
- 日本人はビックリします。
## Slide 34
- 日本の会社の面接で
- 「お給料はいくらほしいですか」
- と聞かれたら
- 何と答えますか？
## Slide 35
- 最初から具体的な
- お金の話はしない
- 方がいいです！
## Slide 36
- 私は日本語もまだまだで経験もありません。
- まずは仕事を
- 頑張りたいです！
## Slide 37
- 御社のルールに
- 従います！
## Slide 38
- これが日本人の
- 感じ方・考え方です！
## Slide 39
- 日本が正しい
- ベトナムが間違えている
## Slide 40
- 日本が変
- 日本人はおかしい
## Slide 41
- SAO KỲ VẬY???
## Slide 42
- 文化・習慣・考え方が
- 違うだけです！
## Slide 43
- 大切なことは
- 日本とベトナムの
- 違いを理解して
- 適切に行動すること

---

# Test xlsx.xlsx (XLSX)
## Sheet: Sheet4 (1000x26)
|  | 試験結果表 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| No. | 受験番号 | 氏名 | 性別 | 学科名 | 日本語 | 数学 | 文学 | 総計 | 結果 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 1.0 | KI2 | のび太　徳田 | A | 教育学科 | 9.0 | 8.5 | 7.5 | 34 | D |  | 問題1： |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 2.0 | KE2 | 優希　カイ | A | 経営学科 | 9.0 | 7.0 | 6.0 | 22 | ROT |  | SUM・H LOOKUP・V LOOKUP・SUMIF・IF・MAX・MINの関数と四則演算を使って： |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 3.0 | NH2 | 勝弘　系 | A | 日本語学科 | 8.0 | 5.0 | 7.0 | 28 | D |  | 性別 |  |  |  |  |  | （10点） |  |  |  |  |  |  |  |  |
| 4.0 | KI1 | 山下　恵子 | U | 教育学科 | 9.0 | 10.0 | 8.5 | 36.5 | D |  | 学科名 |  |  |  |  |  | （10点） |  |  |  |  |  |  |  |  |
| 5.0 | NH1 | 山川　静香 | U | 日本語学科 | 10.0 | 7.0 | 5.0 | 32 | D |  | 総計の点数 |  |  |  |  |  | （15点） |  |  |  |  |  |  |  |  |
| 6.0 | NH1 | 山田　浩 | U | 日本語学科 | 5.0 | 6.0 | 8.0 | 24 | ROT |  | 注： | 経営学科： |  | 日本語＋数学＋文学 |  |  |  |  |  |  |  |  |  |  |  |
| 7.0 | KE2 | 志村　愛 | A | 経営学科 | 7.0 | 7.0 | 8.0 | 22 | ROT |  |  | 日本語学科と教育学科： |  | （日本語*2)＋数学＋文学 |  |  |  |  |  |  |  |  |  |  |  |
## Sheet: Sheet2 (1000x26)
|  | 試験結果表 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| No. | 受験番号 | 氏名 | 性別 | 学科名 | 日本語 | 数学 | 文学 | 総計 | 結果 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 1.0 | KI2 | のび太　徳田 | a | 教育学科 | 9.0 | 8.5 | 7.5 | 34 | dau |  | 問題1： |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 2.0 | KE2 | 優希　カイ | a | 経営学科 | 9.0 | 7.0 | 6.0 | 22 | rot |  | SUM・H LOOKUP・V LOOKUP・SUMIF・IF・MAX・MINの関数と四則演算を使って： |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 3.0 | KE1 | 山下恵美子 | u | 経営学科 | 5.0 | 7.0 | 6.0 | 18 | rot |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 4.0 | NH2 | 勝弘　系 | a | 日本語学科 | 8.0 | 5.0 | 7.0 | 28 | dau |  | 性別 |  |  |  |  |  | （10点） |  |  |  |  |  |  |  |  |
| 5.0 | KE2 | 志村けん | a | 経営学科 | 9.0 | 6.5 | 0.0 | 15.5 | rot |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 6.0 | KI1 | 山下　恵子 | u | 教育学科 | 9.0 | 10.0 | 8.5 | 36.5 | dau |  | 学科名 |  |  |  |  |  | （10点） |  |  |  |  |  |  |  |  |
| 7.0 | NH1 | 山川　静香 | u | 日本語学科 | 10.0 | 7.0 | 5.0 | 32 | dau |  | 総計の点数 |  |  |  |  |  | （15点） |  |  |  |  |  |  |  |  |
## Sheet: Sheet1 (1000x26)
| 試験結果表 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| No. | 受験番号 | 氏名 | 性別 | 学科名 | 日本語 | 数学 | 文学 | 総計 | 結果 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 1.0 | KI2 | のび太　徳田 | 男 | 教育学科 | 9.0 | 8.5 | 7.5 | 34 | 合格 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 2.0 | KE2 | 優希　カイ | 男 | 経営学科 | 9.0 | 7.0 | 6.0 | 22 | 不合格 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 3.0 | KE1 | 山下恵美子 | 女 | 経営学科 | 5.0 | 7.0 | 6.0 | 18 | 不合格 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 4.0 | NH2 | 勝弘　系 | 男 | 日本語学科 | 8.0 | 5.0 | 7.0 | 28 | 合格 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 5.0 | KE2 | 志村けん | 男 | 経営学科 | 9.0 | 6.5 | 0.0 | 15.5 | 不合格 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 6.0 | KI1 | 山下　恵子 | 女 | 教育学科 | 9.0 | 10.0 | 8.5 | 36.5 | 合格 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| 7.0 | NH1 | 山川　静香 | 女 | 日本語学科 | 10.0 | 7.0 | 5.0 | 32 | 合格 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

---
