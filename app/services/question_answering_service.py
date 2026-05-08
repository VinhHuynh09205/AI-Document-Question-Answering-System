import hashlib
import json
import logging
import re
import textwrap
import time
from collections import OrderedDict
from collections.abc import Iterator
from pathlib import Path

from langchain_core.documents import Document

from app.models.entities import AnswerResult
from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.interfaces.llm_provider import ILLMProvider
from app.services.interfaces.question_answering_service import IQuestionAnsweringService
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.qa_constants import FALLBACK_ANSWER


logger = logging.getLogger(__name__)

_MINDMAP_REQUEST_RE = re.compile(
    r"(tao\s*mindmap|tạo\s*mindmap|mind\s*map|so\s*do\s*tu\s*duy|sơ\s*đồ\s*tư\s*duy)",
    re.IGNORECASE,
)
_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*([\s\S]*?)```", re.IGNORECASE)
_MERMAID_GRAPH_DIRECTIVE_RE = re.compile(r"^(\s*)graph(\s+)", re.IGNORECASE)
_MERMAID_LABELED_EDGE_RE = re.compile(
    r"(-->|==>|-.->|---|~~>|--o|o--|--x|x--)[ \t]*\|([^|\n]+)\|[ \t]*>[ \t]*"
)
_MERMAID_LABELED_EDGE_NO_PIPE_RE = re.compile(
    r"(-->|==>|-.->|---|~~>|--o|o--|--x|x--)[ \t]*([^|\n][^>\n]{1,120}?)[ \t]*>[ \t]*"
    r"(?=[A-Za-z0-9_\u00C0-\u024F\u3040-\u30FF\u4E00-\u9FFF-]+[ \t]*[\[(])"
)
_MERMAID_MERGED_EDGE_LINE_RE = re.compile(
    r"([\]\)])([ \t]+)([A-Za-z0-9_][A-Za-z0-9_]*[ \t]*(?:-->|==>|-.->|---|~~>|--o|o--|--x|x--))"
)
_MERMAID_DECLARATION_RE = re.compile(
    r"^\s*(flowchart|graph|mindmap|sequencediagram|classdiagram|erdiagram|gantt|journey|"
    r"statediagram(?:-v2)?|pie|timeline|xychart(?:-beta)?)\b",
    re.IGNORECASE,
)
_MERMAID_EDGE_LINE_RE = re.compile(
    r"^\s*[A-Za-z0-9_\u00C0-\u024F\u3040-\u30FF\u4E00-\u9FFF-]+\s*"
    r"(?:-->|==>|-.->|---|~~>|--o|o--|--x|x--|<--|<==|<-.->)\s*.*$"
)
_MERMAID_NODE_LINE_RE = re.compile(
    r"^\s*[A-Za-z0-9_\u00C0-\u024F\u3040-\u30FF\u4E00-\u9FFF-]+\s*[\[(].*[\])]\s*$"
)
_MERMAID_META_LINE_RE = re.compile(r"^\s*(?:subgraph|end|%%)\b", re.IGNORECASE)
_CODE_FENCE_LINE_RE = re.compile(r"^\s*```")
_FENCED_CODE_BLOCK_RE = re.compile(r"```([^\n`]*)\n([\s\S]*?)```", re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_BULLET_LINE_RE = re.compile(r"^(?:[-*•]|\d+[.)])\s+(.*)$")
_MARKDOWN_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$")
_MARKDOWN_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_COMPLEX_QUESTION_HINT_RE = re.compile(
    r"(so\s*sánh|phân\s*tích|đánh\s*giá|chi\s*tiết|nguyên\s*nhân|hệ\s*quả|"
    r"lộ\s*trình|kế\s*hoạch|why|how|compare|analysis|evaluate|risk|rủi\s*ro)",
    re.IGNORECASE,
)
_VISUAL_ENRICHMENT_HINT_RE = re.compile(
    r"(tom\s*tat|tóm\s*tắt|tong\s*quan|tổng\s*quan|phan\s*tich|phân\s*tích|"
    r"so\s*sanh|compare|liet\s*ke|liệt\s*kê|danh\s*gia|đánh\s*giá|"
    r"bang|bảng|chart|diagram|so\s*do|sơ\s*đồ|mindmap|truc\s*quan|trực\s*quan|"
    r"anh|ảnh|hinh|hình|image|screenshot|figure)",
    re.IGNORECASE,
)
_SIMPLE_FACT_QUESTION_RE = re.compile(
    r"(la\s*gi|là\s*gì|bao\s*nhieu|bao\s*nhiêu|khi\s*nao|ở\s*đâu|"
    r"who|what|when|where|define|định\s*nghĩa|translate|dịch|"
    r"co\s*khong|có\s*không|yes\s*or\s*no)",
    re.IGNORECASE,
)
_TIMELINE_DIAGRAM_HINT_RE = re.compile(
    r"(timeline|thoi\s*gian|thời\s*gian|lo\s*trinh|lộ\s*trình|tien\s*trinh|tiến\s*trình|"
    r"qua\s*trinh|quá\s*trình|giai\s*doan|giai\s*đoạn)",
    re.IGNORECASE,
)
_PIE_DIAGRAM_HINT_RE = re.compile(
    r"(ty\s*le|tỷ\s*lệ|phan\s*tram|phần\s*trăm|phan\s*bo|phân\s*bố|co\s*cau|cơ\s*cấu|pie)",
    re.IGNORECASE,
)
_TABLE_VISUAL_HINT_RE = re.compile(
    r"(so\s*sanh|so\s*sánh|bang|bảng|matrix|ma\s*tran|ma\s*trận|doi\s*chieu|đối\s*chiếu|"
    r"liet\s*ke|liệt\s*kê|tong\s*hop|tổng\s*hợp|phan\s*loai|phân\s*loại)",
    re.IGNORECASE,
)
_FLOWCHART_DIAGRAM_HINT_RE = re.compile(
    r"(quy\s*trinh|quy\s*trình|luong|luồng|flow|process|workflow|pipeline|"
    r"buoc|bước|input|output|dau\s*vao|đầu\s*vào|dau\s*ra|đầu\s*ra|"
    r"if|else|condition|dieu\s*kien|điều\s*kiện)",
    re.IGNORECASE,
)
_MINDMAP_OVERVIEW_HINT_RE = re.compile(
    r"(tong\s*quan|tổng\s*quan|overview|chu\s*de|chủ\s*đề|he\s*thong|hệ\s*thống|"
    r"cau\s*truc|cấu\s*trúc|phan\s*cap|phân\s*cấp|hierarchy)",
    re.IGNORECASE,
)
_DETAIL_VISUAL_HINT_RE = re.compile(
    r"(chi\s*tiet|chi\s*tiết|detail|phan\s*tich|phân\s*tích|danh\s*gia|đánh\s*giá|"
    r"giai\s*thich|giải\s*thích|tieu\s*chi|tiêu\s*chí)",
    re.IGNORECASE,
)
_VISUAL_ENRICHMENT_EXCLUDED_RE = re.compile(
    r"(dịch|dich|translate|định\s*nghĩa|dinh\s*nghia|define|definition|"
    r"quiz|trắc\s*nghiệm|trac\s*nghiem|multiple\s*choice|slide|presentation|"
    r"thuyết\s*trình|thuyet\s*trinh|rút\s*gọn|rut\s*gon|shorten|viết\s*lại|viet\s*lai|"
    r"học\s*thuật|hoc\s*thuat|academic\s*style)",
    re.IGNORECASE,
)
_VISUAL_SECTION_HEADING_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*(?:bảng|bang|sơ\s*đồ|so\s*do|mindmap|diagram|flowchart|biểu\s*đồ|bieu\s*do)\b",
    re.IGNORECASE,
)
_PLAIN_VISUAL_SECTION_HEADING_RE = re.compile(
    r"^\s*(?:bảng|bang|sơ\s*đồ|so\s*do|mindmap|diagram|flowchart|mermaid)"
    r"(?:\s+[\w\u00C0-\u024F\u3040-\u30FF\u4E00-\u9FFF-]+){0,3}\s*[:：]?\s*$",
    re.IGNORECASE,
)
_VISUAL_NOISE_LINE_RE = re.compile(
    r"^\s*(?:\[[^\]]+\]|image\s*\d+\s*:.*|slide\s*image.*|image\s*(?:analysis|insights).*)$",
    re.IGNORECASE,
)
_VISUAL_NOISE_TOKEN_RE = re.compile(
    r"(local_ocr|local_vision|image\s*analysis|slide\s*image|provider[:=])",
    re.IGNORECASE,
)
_MEANINGFUL_TEXT_RE = re.compile(r"[A-Za-z\u00C0-\u024F\u3040-\u30FF\u4E00-\u9FFF]")
_FLOWCHART_DECISION_HINT_RE = re.compile(
    r"(if|else|neu|nếu|yes|no|pass|fail|dieu\s*kien|điều\s*kiện|quyet\s*dinh|quyết\s*định)",
    re.IGNORECASE,
)
_IMAGE_QUESTION_HINT_RE = re.compile(
    r"(anh|ảnh|hinh|hình|image|images|screenshot|screen\s*shot|figure|"
    r"hinh\s*ve|hình\s*vẽ|bieu\s*do\s*trong\s*anh|biểu\s*đồ\s*trong\s*ảnh|"
    r"so\s*do\s*trong\s*anh|sơ\s*đồ\s*trong\s*ảnh|chart\s*in\s*image|diagram\s*in\s*image)",
    re.IGNORECASE,
)
_QUERY_EXPANSION_STOPWORDS = {
    "va", "và", "la", "là", "cua", "của", "cho", "voi", "với", "trong", "tren", "trên",
    "duoc", "được", "nhung", "những", "cac", "các", "mot", "một", "nhu", "như", "the", "thế",
    "nao", "nào", "toi", "tôi", "ban", "bạn", "minh", "mình", "giup", "giúp", "gi", "gì",
    "co", "có", "khong", "không", "tai", "tại", "sao", "khi", "nao", "this", "that", "what",
    "when", "where", "who", "why", "how", "is", "are", "the", "a", "an", "of", "for", "to",
    "and", "or", "in", "on", "from", "with", "about", "please", "help",
}

_QUESTION_REWRITES: list[tuple[re.Pattern[str], str]] = [
    # === Cơ bản ===
    (
        re.compile(r"^(y\s*chinh|ý\s*chính|main\s*points?|key\s*points?)$", re.IGNORECASE),
        "Hãy nêu ý chính của toàn bộ tài liệu dưới dạng gạch đầu dòng ngắn gọn.",
    ),
    (
        re.compile(
            r"^(day\s*la\s*loai\s*tai\s*lieu\s*gi|đây\s*là\s*loại\s*tài\s*liệu\s*gì|loai\s*tai\s*lieu\s*gi|loại\s*tài\s*liệu\s*gì)$",
            re.IGNORECASE,
        ),
        "Tài liệu này thuộc loại gì và chủ đề chính là gì?",
    ),
    (
        re.compile(r"^(trich\s*xuat\s*cac\s*dieu\s*khoan\s*chinh|trích\s*xuất\s*các\s*điều\s*khoản\s*chính)$", re.IGNORECASE),
        "Hãy trích xuất các điểm quan trọng chính trong tài liệu thành danh sách gạch đầu dòng.",
    ),
    (
        re.compile(r"^(tao\s*bang\s*so\s*sanh|tạo\s*bảng\s*so\s*sánh|so\s*sanh\s*cac\s*so\s*lieu\s*quan\s*trong|so\s*sanh\s*các\s*số\s*liệu\s*quan\s*trọng)$", re.IGNORECASE),
        "Hãy tạo bảng so sánh bằng Markdown table chuẩn (header rõ ràng), không dùng bảng ASCII text.",
    ),
    (
        re.compile(r"^(tom\s*tat|tóm\s*tắt|summarize|summary|overview|tong\s*quan|tổng\s*quan)$", re.IGNORECASE),
        "Hãy tóm tắt toàn bộ nội dung tài liệu một cách ngắn gọn, đầy đủ các ý chính.",
    ),
    (
        re.compile(r"^(ket\s*luan|kết\s*luận|conclusion)$", re.IGNORECASE),
        "Hãy nêu kết luận hoặc phần kết thúc của tài liệu.",
    ),
    (
        re.compile(r"^(dinh\s*nghia|định\s*nghĩa|define|definition)[\s:]*(.+)$", re.IGNORECASE),
        "Hãy tìm và giải thích định nghĩa của khái niệm được đề cập trong tài liệu.",
    ),
    (
        re.compile(r"^(liet\s*ke|liệt\s*kê|list\s*all|danh\s*sach|danh\s*sách)[\s:]*(.*)$", re.IGNORECASE),
        "Hãy liệt kê tất cả các mục, danh sách hoặc thông tin quan trọng có trong tài liệu.",
    ),
    (
        re.compile(r"^(giai\s*thich|giải\s*thích|explain)[\s:]*(.+)$", re.IGNORECASE),
        "Hãy giải thích chi tiết nội dung được hỏi dựa trên tài liệu.",
    ),
    (
        re.compile(r"^(so\s*lieu|số\s*liệu|statistics?|data|du\s*lieu|dữ\s*liệu)$", re.IGNORECASE),
        "Hãy trích xuất các số liệu, dữ liệu và thống kê quan trọng có trong tài liệu.",
    ),
    # === 🧠 Phân tích sâu ===
    (
        re.compile(
            r"(uu\s*va\s*nhuoc\s*diem|ưu\s*và\s*nhược\s*điểm|pros?\s*and\s*cons?|advantages?\s*and\s*disadvantages?)",
            re.IGNORECASE,
        ),
        "Hãy phân tích ưu điểm và nhược điểm của nội dung trong tài liệu, trình bày dưới dạng bảng hoặc danh sách rõ ràng.",
    ),
    (
        re.compile(
            r"(diem\s*(gi\s*)?noi\s*bat|điểm\s*(gì\s*)?nổi\s*bật|highlight|outstanding|noi\s*troi|nổi\s*trội)",
            re.IGNORECASE,
        ),
        "Hãy nêu những điểm nổi bật, đặc biệt hoặc khác biệt của tài liệu này so với các tài liệu cùng chủ đề.",
    ),
    (
        re.compile(
            r"(gia\s*dinh|giả\s*định|thien\s*kien|thiên\s*kiến|bias|assumption)",
            re.IGNORECASE,
        ),
        "Hãy phân tích xem tài liệu có chứa giả định, thiên kiến (bias) hoặc quan điểm một chiều nào không. Nêu cụ thể.",
    ),
    (
        re.compile(
            r"(phan\s*nao\s*(la\s*)?quan\s*trong\s*nhat|phần\s*nào\s*(là\s*)?quan\s*trọng\s*nhất|most\s*important\s*part)",
            re.IGNORECASE,
        ),
        "Hãy xác định phần nào trong tài liệu là quan trọng nhất và giải thích lý do tại sao.",
    ),
    # === 📚 Học tập & ghi nhớ ===
    (
        re.compile(
            r"(anh\s*trong\s*tai\s*lieu\s*noi\s*ve\s*cai\s*gi|ảnh\s*trong\s*tài\s*liệu\s*nói\s*về\s*cái\s*gì|"
            r"hinh\s*anh\s*trong\s*tai\s*lieu\s*noi\s*gi|hình\s*ảnh\s*trong\s*tài\s*liệu\s*nói\s*gì|"
            r"anh\s*noi\s*gi|ảnh\s*nói\s*gì|what\s*does\s*the\s*image\s*say)",
            re.IGNORECASE,
        ),
        "Hãy ưu tiên phân tích phần hình ảnh trong tài liệu (ảnh, biểu đồ, sơ đồ, screenshot). Trả lời theo cấu trúc: (1) ảnh thể hiện gì, (2) chi tiết trực quan quan trọng, (3) kết luận chính từ ảnh. Nếu có nhiều ảnh, liệt kê theo từng ảnh/trang.",
    ),
    (
        re.compile(
            r"(tom\s*tat\s*cac\s*anh|tóm\s*tắt\s*các\s*ảnh|tong\s*hop\s*hinh\s*anh|tổng\s*hợp\s*hình\s*ảnh|"
            r"summari[sz]e\s*images?|image\s*summary)",
            re.IGNORECASE,
        ),
        "Hãy tóm tắt toàn bộ hình ảnh trong tài liệu: mỗi ảnh gồm mô tả ngắn, nội dung chính, và ý nghĩa quan trọng.",
    ),
    (
        re.compile(
            r"(phan\s*tich\s*bieu\s*do\s*trong\s*anh|phân\s*tích\s*biểu\s*đồ\s*trong\s*ảnh|"
            r"do\s*thi\s*trong\s*anh|đồ\s*thị\s*trong\s*ảnh|chart\s*in\s*image|analyze\s*chart)",
            re.IGNORECASE,
        ),
        "Hãy phân tích biểu đồ/đồ thị trong ảnh: nêu trục, chỉ số nổi bật, xu hướng tăng giảm, điểm bất thường và kết luận chính.",
    ),
    (
        re.compile(
            r"(giai\s*thich\s*so\s*do\s*trong\s*anh|giải\s*thích\s*sơ\s*đồ\s*trong\s*ảnh|"
            r"flowchart\s*in\s*image|diagram\s*in\s*image|so\s*do\s*luong\s*trong\s*anh)",
            re.IGNORECASE,
        ),
        "Hãy giải thích sơ đồ/luồng trong ảnh theo từng bước: đầu vào, xử lý, đầu ra và các nút quyết định (nếu có).",
    ),
    (
        re.compile(
            r"(anh\s*chup\s*man\s*hinh|ảnh\s*chụp\s*màn\s*hình|giao\s*dien\s*trong\s*anh|giao\s*diện\s*trong\s*ảnh|"
            r"ui\s*screenshot|screen\s*shot\s*ui)",
            re.IGNORECASE,
        ),
        "Hãy mô tả ảnh chụp màn hình/giao diện trong tài liệu: các thành phần chính, trạng thái hiển thị, thao tác người dùng có thể thực hiện.",
    ),

    (
        re.compile(
            r"(tao\s*mindmap|tạo\s*mindmap|mind\s*map|so\s*do\s*tu\s*duy|sơ\s*đồ\s*tư\s*duy)",
            re.IGNORECASE,
        ),
        "Hãy tạo sơ đồ tư duy bằng Mermaid với cú pháp mindmap trong khối ```mermaid``` (không dùng graph/flowchart), có ít nhất 4 nhánh cấp 1 và mỗi nhánh có 2-4 nhánh con, tránh chuỗi tuyến tính một hàng.",
    ),
    (
        re.compile(
            r"(bieu\s*do|biểu\s*đồ|do\s*thi|đồ\s*thị|chart|graph|plot|diagram|so\s*do\s*luong|sơ\s*đồ\s*luồng|flow\s*chart)",
            re.IGNORECASE,
        ),
        "Hãy tự chọn đúng loại trực quan: dùng Markdown table nếu là so sánh/dữ liệu cấu trúc, dùng Mermaid flowchart LR nếu là quy trình hoặc luồng xử lý, dùng Mermaid mindmap nếu là tổng quan phân cấp. Không dùng Mermaid nếu chỉ có 1-2 bước đơn giản.",
    ),
    (
        re.compile(
            r"((tao|tạo|viet|viết)\s*)?(cau\s*hoi\s*trac\s*nghiem|câu\s*hỏi\s*trắc\s*nghiệm|quiz|multiple\s*choice|trac\s*nghiem|trắc\s*nghiệm)",
            re.IGNORECASE,
        ),
        "Hãy tạo 5-10 câu hỏi trắc nghiệm (4 đáp án A/B/C/D) từ nội dung tài liệu, kèm đáp án đúng và giải thích ngắn. Mỗi câu hỏi phải khác nhau, không lặp lại câu hỏi hoặc đáp án, không thêm mục Bảng so sánh hay Mermaid.",
    ),
    (
        re.compile(
            r"(giai\s*thich\s*nhu\s*cho\s*nguoi\s*moi|giải\s*thích\s*như\s*cho\s*người\s*mới|beginner|explain\s*simply|don\s*gian\s*hoa|đơn\s*giản\s*hóa|eli5)",
            re.IGNORECASE,
        ),
        "Hãy giải thích nội dung tài liệu bằng ngôn ngữ đơn giản, dễ hiểu, như đang giải thích cho người mới bắt đầu.",
    ),
    (
        re.compile(
            r"(cho\s*vi\s*du\s*thuc\s*te|cho\s*ví\s*dụ\s*thực\s*tế|real\s*world\s*example|vi\s*du\s*minh\s*hoa|ví\s*dụ\s*minh\s*họa|practical\s*example)",
            re.IGNORECASE,
        ),
        "Hãy cho các ví dụ thực tế, cụ thể liên quan đến nội dung trong tài liệu để dễ hiểu hơn.",
    ),
    # === ✍️ Viết lại / xử lý nội dung ===
    (
        re.compile(
            r"(viet\s*lai.*ngan\s*gon|viết\s*lại.*ngắn\s*gọn|shorten|make\s*it\s*shorter|rut\s*gon|rút\s*gọn)",
            re.IGNORECASE,
        ),
        "Hãy viết lại nội dung tài liệu một cách ngắn gọn hơn, giữ lại các ý chính quan trọng nhất.",
    ),
    (
        re.compile(
            r"(chuyen.*slide|chuyển.*slide|presentation|thuyet\s*trinh|thuyết\s*trình|lam\s*slide|làm\s*slide)",
            re.IGNORECASE,
        ),
        "Hãy chuyển nội dung tài liệu thành dạng slide thuyết trình, mỗi slide gồm tiêu đề và 3-5 bullet points ngắn gọn.",
    ),
    (
        re.compile(
            r"(dich.*sang\s*tieng\s*anh|dịch.*sang\s*tiếng\s*anh|translate.*english)",
            re.IGNORECASE,
        ),
        "Hãy dịch nội dung chính của tài liệu sang tiếng Anh, giữ nguyên ý nghĩa và cấu trúc. Chỉ trả về bản dịch tiếng Anh, không thêm tiếng Việt, không tóm tắt, không bảng Markdown, không Mermaid, không giải thích, không mô tả quyết định trình bày.",
    ),
    (
        re.compile(
            r"(dich.*sang\s*tieng\s*viet|dịch.*sang\s*tiếng\s*việt|translate.*vietnamese)",
            re.IGNORECASE,
        ),
        "Hãy dịch nội dung chính của tài liệu sang tiếng Việt, giữ nguyên ý nghĩa và cấu trúc. Chỉ trả về bản dịch tiếng Việt, không thêm ngôn ngữ khác, không tóm tắt, không bảng Markdown, không Mermaid, không giải thích, không mô tả quyết định trình bày.",
    ),
    (
        re.compile(
            r"(van\s*phong\s*hoc\s*thuat|văn\s*phong\s*học\s*thuật|academic\s*style|hoc\s*thuat\s*hoa|học\s*thuật\s*hóa)",
            re.IGNORECASE,
        ),
        "Hãy viết lại nội dung tài liệu theo văn phong học thuật, chính thống, phù hợp cho bài nghiên cứu hoặc báo cáo.",
    ),
    # === 💻 Áp dụng thực tế ===
    (
        re.compile(
            r"(ap\s*dung.*du\s*an|áp\s*dụng.*dự\s*án|apply.*project|ung\s*dung\s*vao|ứng\s*dụng\s*vào)",
            re.IGNORECASE,
        ),
        "Dựa trên nội dung tài liệu, hãy gợi ý cách áp dụng kiến thức này vào một dự án thực tế, kèm ví dụ cụ thể.",
    ),
    (
        re.compile(
            r"(dung.*trong\s*lap\s*trinh|dùng.*trong\s*lập\s*trình|use.*programming|code\s*example|ap\s*dung.*lap\s*trinh|áp\s*dụng.*lập\s*trình)",
            re.IGNORECASE,
        ),
        "Hãy chỉ ra cách áp dụng nội dung tài liệu trong lập trình, kèm code minh họa nếu có thể.",
    ),
    (
        re.compile(
            r"(case\s*study|tinh\s*huong\s*thuc\s*te|tình\s*huống\s*thực\s*tế|bai\s*hoc\s*thuc\s*te|bài\s*học\s*thực\s*tế)",
            re.IGNORECASE,
        ),
        "Hãy đưa ra một case study hoặc tình huống thực tế liên quan đến nội dung tài liệu để minh họa.",
    ),
    (
        re.compile(
            r"(giai\s*quyet\s*van\s*de\s*gi|giải\s*quyết\s*vấn\s*đề\s*gì|solve\s*what\s*problem|giup\s*gi|giúp\s*gì|useful\s*for)",
            re.IGNORECASE,
        ),
        "Tài liệu này giúp giải quyết vấn đề gì? Hãy nêu các vấn đề cụ thể và cách tài liệu đưa ra giải pháp.",
    ),
    # === 🔍 Kiểm tra & đánh giá ===
    (
        re.compile(
            r"(dang\s*tin\s*khong|đáng\s*tin\s*không|credible|trustworthy|do\s*tin\s*cay|độ\s*tin\s*cậy|reliable)",
            re.IGNORECASE,
        ),
        "Hãy đánh giá độ tin cậy của thông tin trong tài liệu: nguồn dữ liệu có rõ ràng không, có trích dẫn không, có cập nhật không?",
    ),
    (
        re.compile(
            r"(nguon.*uy\s*tin|nguồn.*uy\s*tín|reputable\s*source|reliable\s*source)",
            re.IGNORECASE,
        ),
        "Hãy đánh giá xem nguồn tài liệu này có uy tín không, dựa trên tác giả, tổ chức, năm xuất bản và chất lượng nội dung.",
    ),
    (
        re.compile(
            r"(loi\s*logic|lỗi\s*logic|sai\s*sot|sai\s*sót|logical?\s*error|mistake|inconsistenc)",
            re.IGNORECASE,
        ),
        "Hãy kiểm tra tài liệu xem có lỗi logic, mâu thuẫn, hoặc sai sót nào trong nội dung không. Nêu cụ thể nếu có.",
    ),
    (
        re.compile(
            r"(so\s*sanh\s*voi\s*tai\s*lieu\s*khac|so\s*sánh\s*với\s*tài\s*liệu\s*khác|compare\s*with\s*other)",
            re.IGNORECASE,
        ),
        "Hãy phân tích và nêu những điểm mà tài liệu này có thể khác biệt hoặc bổ sung so với các tài liệu cùng chủ đề.",
    ),
]


class QuestionAnsweringService(IQuestionAnsweringService):
    def __init__(
        self,
        vector_store_repository: IVectorStoreRepository,
        llm_provider: ILLMProvider,
        backup_llm_provider: ILLMProvider | None,
        top_k: int,
        min_context_token_overlap: float,
        min_relevant_chunks: int,
        cache_ttl_seconds: int = 300,
        cache_max_size: int = 128,
        runtime_metrics: IRuntimeMetrics | None = None,
        hybrid_retrieval_enabled: bool = True,
        reranking_enabled: bool = True,
    ) -> None:
        self._vector_store_repository = vector_store_repository
        self._llm_provider = llm_provider
        self._backup_llm_provider = backup_llm_provider
        self._top_k = top_k
        self._min_context_token_overlap = min_context_token_overlap
        self._min_relevant_chunks = min_relevant_chunks
        self._cache: OrderedDict[str, tuple[float, AnswerResult]] = OrderedDict()
        self._cache_ttl = cache_ttl_seconds
        self._cache_max_size = cache_max_size
        self._runtime_metrics = runtime_metrics
        self._hybrid_retrieval_enabled = bool(hybrid_retrieval_enabled)
        self._reranking_enabled = bool(reranking_enabled)

    @staticmethod
    def _build_cache_key(
        raw_question: str,
        normalized_question: str,
        metadata_filter: dict[str, str | list[str]] | None,
        top_k: int,
    ) -> str:
        raw = json.dumps(
            {
                "rq": raw_question,
                "q": normalized_question,
                "f": metadata_filter or {},
                "k": top_k,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_cached(self, key: str) -> AnswerResult | None:
        if key not in self._cache:
            return None
        ts, result = self._cache[key]
        if time.monotonic() - ts > self._cache_ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return result

    def _put_cache(self, key: str, result: AnswerResult) -> None:
        if self._cache_ttl <= 0:
            return
        self._cache[key] = (time.monotonic(), result)
        while len(self._cache) > self._cache_max_size:
            self._cache.popitem(last=False)

    def ask(
        self,
        question: str,
        metadata_filter: dict[str, str | list[str]] | None = None,
        top_k: int | None = None,
    ) -> AnswerResult:
        raw_question = self._normalize_text_query(question)
        normalized_question = self._normalize_question(raw_question)
        effective_top_k = self._resolve_effective_top_k(raw_question, top_k)
        is_mindmap_request = self._is_mindmap_request(question, normalized_question)

        cache_key = self._build_cache_key(
            raw_question,
            normalized_question,
            metadata_filter,
            effective_top_k,
        )
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.info("qa_cache_hit key=%s", cache_key[:12])
            return cached

        try:
            context_docs = self._retrieve_context_docs(
                raw_question=raw_question,
                normalized_question=normalized_question,
                metadata_filter=metadata_filter,
                top_k=effective_top_k,
            )
        except Exception:
            logger.exception("qa_retrieval_failed")
            return AnswerResult(answer=FALLBACK_ANSWER, sources=[], context_found=False)

        context_docs = [doc for doc in context_docs if doc.page_content.strip()]
        if not context_docs:
            logger.info("qa_no_context_docs_retrieved")
            return AnswerResult(answer=FALLBACK_ANSWER, sources=[], context_found=False)

        relevant_docs = self._filter_relevant_context(normalized_question, context_docs)

        if len(relevant_docs) < self._min_relevant_chunks:
            logger.info(
                "qa_overlap_filter_relaxed total_docs=%s relevant_docs=%s",
                len(context_docs),
                len(relevant_docs),
            )
            relevant_docs = context_docs

        answer = self._generate_answer_with_fallback(normalized_question, relevant_docs)
        answer = self._strip_presentation_meta(answer)
        answer = self._normalize_mermaid_answer(answer)

        if is_mindmap_request and answer and not self._is_fallback_answer(answer):
            answer = self._ensure_mindmap_answer(answer, relevant_docs, normalized_question)
        elif answer and not self._is_fallback_answer(answer):
            answer = self._ensure_visual_answer(answer, relevant_docs, normalized_question)

        if not answer or self._is_fallback_answer(answer):
            logger.info("qa_answer_fallback_triggered")
            return AnswerResult(answer=FALLBACK_ANSWER, sources=[], context_found=False)

        logger.info("qa_answer_generated sources=%s", len(relevant_docs))
        result = AnswerResult(
            answer=answer,
            sources=self._extract_sources(relevant_docs),
            context_found=True,
        )
        self._put_cache(cache_key, result)
        return result

    def ask_stream(
        self,
        question: str,
        metadata_filter: dict[str, str | list[str]] | None = None,
        top_k: int | None = None,
    ) -> Iterator[str]:
        raw_question = self._normalize_text_query(question)
        normalized_question = self._normalize_question(raw_question)
        effective_top_k = self._resolve_effective_top_k(raw_question, top_k)
        is_mindmap_request = self._is_mindmap_request(question, normalized_question)

        try:
            context_docs = self._retrieve_context_docs(
                raw_question=raw_question,
                normalized_question=normalized_question,
                metadata_filter=metadata_filter,
                top_k=effective_top_k,
            )
        except Exception:
            logger.exception("qa_stream_retrieval_failed")
            yield FALLBACK_ANSWER
            return

        context_docs = [doc for doc in context_docs if doc.page_content.strip()]
        if not context_docs:
            yield FALLBACK_ANSWER
            return

        relevant_docs = self._filter_relevant_context(normalized_question, context_docs)
        if len(relevant_docs) < self._min_relevant_chunks:
            relevant_docs = context_docs

        answer = self._generate_answer_with_fallback(normalized_question, relevant_docs)
        answer = self._strip_presentation_meta(answer)
        answer = self._normalize_mermaid_answer(answer)
        if not answer or self._is_fallback_answer(answer):
            yield FALLBACK_ANSWER
            return

        if is_mindmap_request:
            answer = self._ensure_mindmap_answer(answer, relevant_docs, normalized_question)
        else:
            answer = self._ensure_visual_answer(answer, relevant_docs, normalized_question)

        if not answer or self._is_fallback_answer(answer):
            yield FALLBACK_ANSWER
            return

        yield answer

    def _ensure_visual_answer(
        self,
        answer: str,
        context_docs: list[Document],
        normalized_question: str,
    ) -> str:
        cleaned_answer = self._remove_unfenced_mermaid_snippets(answer).strip()
        question_text = str(normalized_question or "").lower()

        if _VISUAL_ENRICHMENT_EXCLUDED_RE.search(question_text):
            return self._sanitize_non_visual_answer(cleaned_answer)

        if _SIMPLE_FACT_QUESTION_RE.search(question_text) and not _VISUAL_ENRICHMENT_HINT_RE.search(question_text):
            return self._sanitize_non_visual_answer(cleaned_answer)

        original_table_heavy = self._is_table_heavy_answer(cleaned_answer)
        explicit_table_request = self._is_explicit_table_request(normalized_question)

        if original_table_heavy:
            cleaned_answer = self._strip_markdown_tables(cleaned_answer).strip()

        has_table = self._has_markdown_table(cleaned_answer)
        has_mermaid = self._extract_mermaid_block(cleaned_answer) is not None

        branches = self._collect_visual_branches(answer, context_docs)

        if original_table_heavy:
            cleaned_answer = self._ensure_narrative_lead(cleaned_answer, branches)

        if not self._should_enrich_visual_answer(
            normalized_question,
            cleaned_answer,
            has_table=has_table,
            has_mermaid=has_mermaid,
        ):
            return cleaned_answer

        add_summary, table_variant, mermaid_variant = self._build_visual_plan(
            normalized_question,
            branches,
        )

        if original_table_heavy and not explicit_table_request:
            table_variant = None

        additions: list[str] = []

        if add_summary and not self._has_bullet_points(cleaned_answer):
            quick_summary = self._build_summary_bullets(branches)
            if quick_summary:
                additions.append(f"### Tóm tắt nhanh\n{quick_summary}")

        table_section = self._build_table_section(
            branches,
            table_variant,
        )
        if table_section and not has_table:
            additions.append(table_section)

        mermaid_section = self._build_mermaid_section(
            branches,
            normalized_question,
            context_docs,
            mermaid_variant,
        )
        if mermaid_section and not has_mermaid:
            additions.append(mermaid_section)

        if not additions:
            return cleaned_answer

        joined_additions = "\n\n".join(additions)
        return f"{cleaned_answer}\n\n{joined_additions}".strip()

    def _sanitize_non_visual_answer(self, answer: str) -> str:
        compact = self._strip_mermaid_noise(answer)
        compact = self._strip_markdown_tables(compact)
        compact = self._strip_pipe_table_blocks(compact)
        compact = self._strip_visual_section_headings(compact)
        compact = "\n".join(line.rstrip() for line in compact.splitlines()).strip()
        return re.sub(r"\n{3,}", "\n\n", compact)

    @staticmethod
    def _strip_pipe_table_blocks(answer: str) -> str:
        lines = [line.rstrip() for line in str(answer or "").splitlines()]
        cleaned_lines: list[str] = []
        index = 0

        while index < len(lines):
            if _MARKDOWN_TABLE_ROW_RE.match(lines[index]):
                index += 1
                while index < len(lines) and _MARKDOWN_TABLE_ROW_RE.match(lines[index]):
                    index += 1
                continue

            cleaned_lines.append(lines[index])
            index += 1

        return "\n".join(cleaned_lines)

    @staticmethod
    def _strip_visual_section_headings(answer: str) -> str:
        kept_lines: list[str] = []
        for line in str(answer or "").splitlines():
            if _VISUAL_SECTION_HEADING_RE.match(line) or _PLAIN_VISUAL_SECTION_HEADING_RE.match(line):
                continue
            kept_lines.append(line)
        return "\n".join(kept_lines)

    def _build_visual_plan(
        self,
        normalized_question: str,
        branches: OrderedDict[str, list[str]],
    ) -> tuple[bool, str | None, str | None]:
        question_text = str(normalized_question or "").lower()
        entries = self._build_visual_entries(branches, max_entries=6, max_children=3)
        if not entries:
            return False, None, None

        branch_count = len(entries)
        total_children = sum(len(child_labels) for _, child_labels in entries)
        average_children = total_children / branch_count if branch_count else 0.0

        wants_table = self._is_explicit_table_request(question_text)
        wants_flowchart = bool(_FLOWCHART_DIAGRAM_HINT_RE.search(question_text)) or self._looks_like_sequential_entries(entries)
        wants_mindmap = bool(_MINDMAP_REQUEST_RE.search(question_text) or _MINDMAP_OVERVIEW_HINT_RE.search(question_text))
        wants_detail = bool(_DETAIL_VISUAL_HINT_RE.search(question_text) or _COMPLEX_QUESTION_HINT_RE.search(question_text))
        structured_entries = branch_count >= 2 and (average_children >= 1 or branch_count >= 4)

        table_variant: str | None = None
        if structured_entries and wants_table:
            table_variant = "matrix" if wants_table else "overview"

        mermaid_variant: str | None = None
        if wants_flowchart and not self._is_too_simple_for_flowchart(entries):
            mermaid_variant = "flowchart"
        elif wants_mindmap or (branch_count >= 4 and average_children >= 1.25 and not wants_table):
            mermaid_variant = "mindmap"

        if mermaid_variant == "mindmap" and branch_count < 3:
            mermaid_variant = None

        return bool(table_variant or mermaid_variant), table_variant, mermaid_variant

    def _ensure_narrative_lead(
        self,
        answer: str,
        branches: OrderedDict[str, list[str]],
    ) -> str:
        cleaned_answer = str(answer or "").strip()
        if len(self._tokenize(cleaned_answer)) >= 30:
            return cleaned_answer

        narrative = self._build_narrative_summary(branches)
        if not narrative:
            return cleaned_answer
        if not cleaned_answer:
            return narrative
        return f"{narrative}\n\n{cleaned_answer}".strip()

    def _build_narrative_summary(
        self,
        branches: OrderedDict[str, list[str]],
    ) -> str:
        clauses: list[str] = []

        for branch, children in list(branches.items())[:3]:
            branch_label = self._clean_mindmap_label(branch)
            if not branch_label:
                continue

            child_labels = [
                self._clean_mindmap_label(child)
                for child in children[:2]
                if self._clean_mindmap_label(child)
            ]
            if child_labels:
                clauses.append(f"{branch_label} gồm {', '.join(child_labels)}")
            else:
                clauses.append(branch_label)

        if not clauses:
            return ""

        return "Nội dung chính tập trung vào " + "; ".join(clauses) + "."

    @staticmethod
    def _count_non_table_tokens(answer: str) -> int:
        lines = [line for line in str(answer or "").splitlines() if line.strip()]
        non_table_lines = [line for line in lines if "|" not in line.strip()]
        return len(QuestionAnsweringService._tokenize("\n".join(non_table_lines)))

    @staticmethod
    def _count_markdown_tables(answer: str) -> int:
        count = 0
        lines = [line.rstrip() for line in str(answer or "").splitlines()]
        index = 0
        while index < len(lines) - 1:
            if _MARKDOWN_TABLE_ROW_RE.match(lines[index]) and _MARKDOWN_TABLE_SEPARATOR_RE.match(lines[index + 1]):
                count += 1
                index += 2
                while index < len(lines) and _MARKDOWN_TABLE_ROW_RE.match(lines[index]):
                    index += 1
                continue
            index += 1
        return count

    @staticmethod
    def _is_table_heavy_answer(answer: str) -> bool:
        table_count = QuestionAnsweringService._count_markdown_tables(answer)
        if table_count == 0:
            return False

        non_table_tokens = QuestionAnsweringService._count_non_table_tokens(answer)
        return table_count >= 2 or non_table_tokens < 28

    @staticmethod
    def _strip_markdown_tables(answer: str) -> str:
        lines = [line.rstrip() for line in str(answer or "").splitlines()]
        cleaned_lines: list[str] = []
        index = 0

        while index < len(lines):
            if (
                index < len(lines) - 1
                and _MARKDOWN_TABLE_ROW_RE.match(lines[index])
                and _MARKDOWN_TABLE_SEPARATOR_RE.match(lines[index + 1])
            ):
                index += 2
                while index < len(lines) and _MARKDOWN_TABLE_ROW_RE.match(lines[index]):
                    index += 1
                continue

            cleaned_lines.append(lines[index])
            index += 1

        compact = "\n".join(cleaned_lines).strip()
        return re.sub(r"\n{3,}", "\n\n", compact)

    @staticmethod
    def _is_explicit_table_request(question_text: str) -> bool:
        return bool(
            re.search(
                r"(so\s*sanh|so\s*sánh|compare|bảng|bang|table|matrix|ma\s*tran|ma\s*trận|"
                r"doi\s*chieu|đối\s*chiếu|thuoc\s*tinh|thuộc\s*tính|tieu\s*chi|tiêu\s*chí)",
                str(question_text or ""),
                re.IGNORECASE,
            )
        )

    def _build_table_section(
        self,
        branches: OrderedDict[str, list[str]],
        table_variant: str | None,
    ) -> str:
        if table_variant == "matrix":
            matrix_table = self._build_matrix_table(branches)
            if matrix_table:
                return f"### Bảng so sánh\n{matrix_table}"

        if table_variant == "overview":
            overview_table = self._build_overview_table(branches)
            if overview_table:
                return f"### Bảng tổng hợp\n{overview_table}"

        return ""

    def _build_mermaid_section(
        self,
        branches: OrderedDict[str, list[str]],
        normalized_question: str,
        context_docs: list[Document],
        mermaid_variant: str | None,
    ) -> str:
        if mermaid_variant == "mindmap":
            mindmap_block = self._build_supplementary_mindmap_block(
                branches,
                normalized_question,
                context_docs,
            )
            if mindmap_block:
                return f"### Mindmap chủ đề\n{mindmap_block}"

        if mermaid_variant == "flowchart":
            entries = self._build_visual_entries(branches, max_entries=5, max_children=2)
            if len(entries) < 3:
                return ""

            root_label = self._derive_visual_root(normalized_question, context_docs)
            flowchart_block = self._build_flowchart_diagram_block(entries, root_label)
            if flowchart_block:
                return f"### Sơ đồ quy trình\n{flowchart_block}"

        return ""

    @staticmethod
    def _is_too_simple_for_flowchart(entries: list[tuple[str, list[str]]]) -> bool:
        if len(entries) > 2:
            return False
        return all(len(child_labels) <= 1 for _, child_labels in entries)

    @staticmethod
    def _should_enrich_visual_answer(
        normalized_question: str,
        answer: str,
        *,
        has_table: bool,
        has_mermaid: bool,
    ) -> bool:
        question_text = str(normalized_question or "").lower()
        answer_tokens = QuestionAnsweringService._tokenize(answer)
        question_tokens = QuestionAnsweringService._tokenize(question_text)

        if _VISUAL_ENRICHMENT_EXCLUDED_RE.search(question_text):
            return False

        has_visual_hint = bool(_VISUAL_ENRICHMENT_HINT_RE.search(question_text))
        has_complex_hint = bool(_COMPLEX_QUESTION_HINT_RE.search(question_text))
        is_simple_fact = bool(_SIMPLE_FACT_QUESTION_RE.search(question_text))

        if is_simple_fact and not has_visual_hint:
            return False

        if has_visual_hint:
            return True

        if has_table or has_mermaid:
            return len(answer_tokens) >= 45

        if has_complex_hint and len(answer_tokens) >= 35:
            return True

        if len(question_tokens) >= 14 and len(answer_tokens) >= 55:
            return True

        return False

    def _collect_visual_branches(
        self,
        answer: str,
        context_docs: list[Document],
    ) -> OrderedDict[str, list[str]]:
        branches = self._collect_branches_from_answer(answer)

        for branch, children in self._collect_branches_from_context(context_docs).items():
            if branch not in branches:
                branches[branch] = list(children)
            else:
                for child in children:
                    self._append_branch(branches, branch, child)

            if len(branches) >= 10:
                break

        return branches

    @staticmethod
    def _has_bullet_points(answer: str) -> bool:
        return any(_BULLET_LINE_RE.match(line.strip()) for line in answer.splitlines())

    @staticmethod
    def _has_markdown_table(answer: str) -> bool:
        lines = [line.rstrip() for line in answer.splitlines()]
        for index in range(len(lines) - 1):
            if _MARKDOWN_TABLE_ROW_RE.match(lines[index]) and _MARKDOWN_TABLE_SEPARATOR_RE.match(lines[index + 1]):
                return True
        return False

    def _build_summary_bullets(self, branches: OrderedDict[str, list[str]]) -> str:
        lines: list[str] = []

        for branch, children in list(branches.items())[:6]:
            branch_label = self._clean_mindmap_label(branch)
            if not branch_label:
                continue

            child_labels: list[str] = []
            for child in children[:2]:
                child_label = self._clean_mindmap_label(child)
                if child_label:
                    child_labels.append(child_label)

            if child_labels:
                lines.append(f"- **{branch_label}**: {', '.join(child_labels)}")
            else:
                lines.append(f"- **{branch_label}**")

        return "\n".join(lines)

    def _build_overview_table(self, branches: OrderedDict[str, list[str]]) -> str:
        rows: list[str] = []

        for branch, children in list(branches.items())[:8]:
            branch_label = self._clean_mindmap_label(branch)
            if not branch_label:
                continue

            child_labels: list[str] = []
            for child in children[:3]:
                child_label = self._clean_mindmap_label(child)
                if child_label:
                    child_labels.append(child_label)

            detail = ", ".join(child_labels) if child_labels else "Nội dung chính trong tài liệu"
            rows.append(
                f"| {self._escape_table_cell(branch_label)} | {self._escape_table_cell(detail)} |"
            )

        if len(rows) < 2:
            return ""

        return "\n".join(
            [
                "| Chủ đề | Điểm chính |",
                "|---|---|",
                *rows,
            ]
        )

    def _build_matrix_table(self, branches: OrderedDict[str, list[str]]) -> str:
        rows: list[str] = []

        for branch, children in list(branches.items())[:6]:
            branch_label = self._clean_mindmap_label(branch)
            if not branch_label:
                continue

            child_labels = [
                self._clean_mindmap_label(child)
                for child in children[:2]
                if self._clean_mindmap_label(child)
            ]
            detail = " / ".join(child_labels) if child_labels else "Nội dung chính"
            rows.append(
                "| "
                + self._escape_table_cell(branch_label)
                + " | "
                + self._escape_table_cell(detail)
                + " | "
                + str(max(1, len(child_labels)))
                + " |"
            )

        if len(rows) < 3:
            return ""

        return "\n".join(
            [
                "| Nhóm nội dung | Chi tiết tiêu biểu | Số ý chính |",
                "|---|---|---:|",
                *rows,
            ]
        )

    def _build_visual_entries(
        self,
        branches: OrderedDict[str, list[str]],
        *,
        max_entries: int = 6,
        max_children: int = 2,
    ) -> list[tuple[str, list[str]]]:
        entries: list[tuple[str, list[str]]] = []

        for branch, children in list(branches.items())[:max_entries]:
            branch_label = self._clean_mindmap_label(branch)
            if not branch_label:
                continue

            child_labels: list[str] = []
            for child in children[:max_children]:
                child_label = self._clean_mindmap_label(child)
                if child_label:
                    child_labels.append(child_label)

            entries.append((branch_label, child_labels))

        return entries

    def _build_overview_diagram_block(
        self,
        branches: OrderedDict[str, list[str]],
        normalized_question: str,
        context_docs: list[Document],
    ) -> str:
        entries = self._build_visual_entries(branches)

        if len(entries) < 2:
            return ""

        root_label = self._derive_visual_root(normalized_question, context_docs)
        diagram_type = self._select_overview_diagram_type(normalized_question, entries)

        if diagram_type == "mindmap":
            mindmap_block = self._build_visual_mindmap_diagram_block(entries, root_label)
            if mindmap_block:
                return mindmap_block

        return self._build_flowchart_diagram_block(entries, root_label)

    def _build_supplementary_mindmap_block(
        self,
        branches: OrderedDict[str, list[str]],
        normalized_question: str,
        context_docs: list[Document],
    ) -> str:
        entries = self._build_visual_entries(branches, max_entries=3, max_children=2)
        if len(entries) < 3:
            return ""

        root_label = self._derive_visual_root(normalized_question, context_docs)
        return self._build_visual_mindmap_diagram_block(entries, root_label)

    def _build_supplementary_pie_block(
        self,
        branches: OrderedDict[str, list[str]],
        normalized_question: str,
        context_docs: list[Document],
    ) -> str:
        entries = self._build_visual_entries(branches, max_entries=5, max_children=3)
        if len(entries) < 3:
            return ""

        root_label = self._derive_visual_root(normalized_question, context_docs)
        return self._build_pie_diagram_block(entries, root_label)

    def _select_overview_diagram_type(
        self,
        normalized_question: str,
        entries: list[tuple[str, list[str]]],
    ) -> str:
        question_text = str(normalized_question or "").lower()

        if _MINDMAP_REQUEST_RE.search(question_text) or _MINDMAP_OVERVIEW_HINT_RE.search(question_text):
            return "mindmap"

        if _FLOWCHART_DIAGRAM_HINT_RE.search(question_text) or self._looks_like_sequential_entries(entries):
            return "flowchart"

        total_children = sum(len(child_labels) for _, child_labels in entries)
        average_children = total_children / len(entries) if entries else 0.0
        if len(entries) >= 4 and average_children >= 1.25:
            return "mindmap"

        return "flowchart"

    @staticmethod
    def _looks_like_sequential_entries(entries: list[tuple[str, list[str]]]) -> bool:
        if len(entries) < 2:
            return False

        sequential_hint_count = 0
        ordered_prefix_count = 0
        for branch_label, child_labels in entries:
            normalized = QuestionAnsweringService._normalize_text_query(branch_label).lower()
            if re.search(
                r"\b(buoc|bước|giai doan|giai đoạn|phase|step|stage|quy trinh|quy trình|"
                r"thuc hien|thực hiện|xu ly|xử lý|kiem tra|kiểm tra|danh gia|đánh giá)\b",
                normalized,
            ):
                sequential_hint_count += 1
            if re.match(
                r"^(?:buoc|bước|giai doan|giai đoạn|phase|step|stage)\s*\d+\b|^\d+[.)-]?\s*",
                normalized,
            ):
                ordered_prefix_count += 1

        return ordered_prefix_count >= 2 or sequential_hint_count >= max(2, len(entries) - 1)

    def _build_flowchart_diagram_block(
        self,
        entries: list[tuple[str, list[str]]],
        root_label: str,
    ) -> str:
        normalized_entries: list[tuple[str, list[str]]] = []
        for branch_label, child_labels in entries:
            compact_branch = self._compact_visual_label(branch_label)
            compact_children = [
                compact_child
                for child_label in child_labels
                if (compact_child := self._compact_visual_label(child_label))
            ]
            if compact_branch:
                normalized_entries.append((compact_branch, compact_children))

        if len(normalized_entries) < 2:
            return ""

        branch_ids: list[str] = []
        detail_ids: list[str] = []
        decision_ids: list[str] = []
        lines = [
            "```mermaid",
            "flowchart LR",
            "  classDef terminal fill:#0f766e,stroke:#115e59,color:#ffffff,stroke-width:2.4px",
            "  classDef branch fill:#ecfeff,stroke:#14b8a6,color:#0f172a,stroke-width:1.8px",
            "  classDef detail fill:#ffffff,stroke:#94a3b8,color:#0f172a,stroke-width:1.3px",
            "  classDef decision fill:#fef3c7,stroke:#f59e0b,color:#7c2d12,stroke-width:1.8px",
        ]

        start_label = self._compact_visual_label(root_label)
        start_node = self._format_flowchart_node("S", start_label, shape="terminal", width=14)
        if not start_node:
            return ""
        lines.append(start_node)

        is_sequential_flow = self._looks_like_sequential_entries(normalized_entries)
        if not is_sequential_flow and len(normalized_entries) == 2:
            is_sequential_flow = bool(_FLOWCHART_DIAGRAM_HINT_RE.search(str(root_label or "")))

        if is_sequential_flow:
            previous_id = "S"
            for index, (branch_label, child_labels) in enumerate(normalized_entries, start=1):
                branch_id = f"B{index}"
                branch_ids.append(branch_id)
                node_shape = "decision" if self._is_decision_like_label(branch_label) else "process"
                if node_shape == "decision":
                    decision_ids.append(branch_id)
                lines.append(self._format_flowchart_node(branch_id, branch_label, shape=node_shape, width=14))
                lines.append(f"  {previous_id} -->|bước {index}| {branch_id}")

                for child_index, child_label in enumerate(child_labels[:1], start=1):
                    child_id = f"{branch_id}_{child_index}"
                    detail_ids.append(child_id)
                    lines.append(self._format_flowchart_node(child_id, child_label, shape="process", width=12))
                    lines.append(f"  {branch_id} -->|chi tiết| {child_id}")

                previous_id = branch_id

            lines.append(self._format_flowchart_node("E", "Hoàn tất", shape="terminal", width=10))
            lines.append(f"  {previous_id} -->|kết quả| E")
        else:
            for index, (branch_label, child_labels) in enumerate(normalized_entries, start=1):
                branch_id = f"B{index}"
                branch_ids.append(branch_id)
                node_shape = "decision" if self._is_decision_like_label(branch_label) else "process"
                if node_shape == "decision":
                    decision_ids.append(branch_id)
                lines.append(self._format_flowchart_node(branch_id, branch_label, shape=node_shape, width=14))
                lines.append(f"  S -->|nhánh {index}| {branch_id}")

                for child_index, child_label in enumerate(child_labels[:2], start=1):
                    child_id = f"{branch_id}_{child_index}"
                    detail_ids.append(child_id)
                    lines.append(self._format_flowchart_node(child_id, child_label, shape="process", width=12))
                    lines.append(f"  {branch_id} -->|chi tiết| {child_id}")

        lines.append("  class S,E terminal")
        if branch_ids:
            lines.append(f"  class {','.join(branch_ids)} branch")
        if detail_ids:
            lines.append(f"  class {','.join(detail_ids)} detail")
        if decision_ids:
            lines.append(f"  class {','.join(decision_ids)} decision")
        lines.append("  linkStyle default stroke:#0f766e,stroke-width:2px,fill:none,opacity:0.82")

        lines.append("```")
        return "\n".join(lines)

    def _build_visual_mindmap_diagram_block(
        self,
        entries: list[tuple[str, list[str]]],
        root_label: str,
    ) -> str:
        compact_root = self._compact_visual_label(root_label)
        if not compact_root:
            return ""

        lines = [
            "```mermaid",
            "mindmap",
            f"  root(({compact_root}))",
        ]

        total_nodes = 1

        for branch_label, child_labels in entries:
            branch = self._compact_visual_label(branch_label, max_words=4, max_chars=28)
            if not branch or total_nodes >= 10:
                continue

            lines.append(f"    {branch}")
            total_nodes += 1
            remaining_nodes = 10 - total_nodes
            if remaining_nodes <= 0:
                break

            for child_label in child_labels[: min(2, remaining_nodes)]:
                child = self._compact_visual_label(child_label, max_words=4, max_chars=24)
                if child:
                    lines.append(f"      {child}")
                    total_nodes += 1
                    if total_nodes >= 10:
                        break

        lines.append("```")
        return "\n".join(lines)

    def _build_timeline_diagram_block(
        self,
        entries: list[tuple[str, list[str]]],
        root_label: str,
    ) -> str:
        if len(entries) < 2:
            return ""

        lines = [
            "```mermaid",
            "timeline",
            f"  title {self._clean_mindmap_label(root_label)}",
        ]

        for index, (branch_label, child_labels) in enumerate(entries, start=1):
            stage_label = self._clean_mindmap_label(branch_label) or f"Giai doan {index}"
            if child_labels:
                detail = " | ".join(self._clean_mindmap_label(child) for child in child_labels if self._clean_mindmap_label(child))
            else:
                detail = "Noi dung chinh"

            lines.append(f"  {stage_label} : {detail}")

        lines.append("```")
        return "\n".join(lines)

    def _build_pie_diagram_block(
        self,
        entries: list[tuple[str, list[str]]],
        root_label: str,
    ) -> str:
        if len(entries) < 2:
            return ""

        scored_entries: list[tuple[str, int]] = []
        for branch_label, child_labels in entries:
            branch = self._clean_mindmap_label(branch_label)
            if not branch:
                continue
            score = max(1, len([child for child in child_labels if self._clean_mindmap_label(child)]))
            scored_entries.append((branch, score))

        if len(scored_entries) < 2:
            return ""

        lines = [
            "```mermaid",
            "pie showData",
            f"  title {self._clean_mindmap_label(root_label)}",
        ]

        for branch, score in scored_entries:
            lines.append(f'  "{self._escape_mermaid_label(branch)}" : {score}')

        lines.append("```")
        return "\n".join(lines)

    @staticmethod
    def _derive_visual_root(normalized_question: str, context_docs: list[Document]) -> str:
        source_name = ""
        if context_docs:
            source_name = Path(str(context_docs[0].metadata.get("source", ""))).name
            if "_" in source_name and len(source_name.split("_", 1)[0]) == 32:
                source_name = source_name.split("_", 1)[1]

        if source_name:
            root = f"Tổng quan {source_name}"
        elif normalized_question:
            root = f"Tổng quan: {normalized_question[:60]}"
        else:
            root = "Tổng quan tài liệu"

        return QuestionAnsweringService._clean_mindmap_label(root)

    @staticmethod
    def _escape_table_cell(value: str) -> str:
        return str(value or "").replace("|", "\\|").strip()

    @staticmethod
    def _escape_mermaid_label(value: str) -> str:
        return str(value or "").replace('"', "\\\"").strip()

    @classmethod
    def _compact_visual_label(
        cls,
        value: str,
        *,
        max_words: int = 6,
        max_chars: int = 42,
    ) -> str:
        normalized = cls._clean_mindmap_label(value)
        if not normalized:
            return ""

        words = normalized.split()
        compact = " ".join(words[:max_words])
        if len(compact) > max_chars:
            truncated = compact[:max_chars].rstrip(" ,;:-")
            compact = truncated.rsplit(" ", 1)[0] or truncated

        return compact.strip(" ,;:-")

    @classmethod
    def _format_mermaid_node_label(cls, value: str, *, width: int = 18) -> str:
        escaped = cls._escape_mermaid_label(cls._compact_visual_label(value, max_chars=max(width * 3, 24)))
        if not escaped or len(escaped) <= width or " " not in escaped:
            return escaped

        wrapped_lines = textwrap.wrap(
            escaped,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        if len(wrapped_lines) <= 1:
            return escaped

        return "<br/>".join(line.strip() for line in wrapped_lines if line.strip())

    @classmethod
    def _format_flowchart_node(
        cls,
        node_id: str,
        label: str,
        *,
        shape: str = "process",
        width: int = 14,
    ) -> str:
        formatted_label = cls._format_mermaid_node_label(label, width=width)
        if not formatted_label:
            return ""

        if shape == "terminal":
            return f'  {node_id}("{formatted_label}")'
        if shape == "decision":
            return f'  {node_id}{{"{formatted_label}"}}'
        return f'  {node_id}["{formatted_label}"]'

    @staticmethod
    def _is_decision_like_label(value: str) -> bool:
        return bool(_FLOWCHART_DECISION_HINT_RE.search(str(value or "")))

    @staticmethod
    def _strip_presentation_meta(answer: str) -> str:
        text = str(answer or "").strip()
        if not text:
            return text

        blocks = re.split(r"\n\s*\n", text, maxsplit=1)
        if not blocks:
            return text

        first_block = blocks[0].strip()
        if re.search(
            r"(tôi\s*quyết\s*định|toi\s*quyet\s*dinh|dựa\s*trên\s*nội\s*dung|dua\s*tren\s*noi\s*dung|"
            r"trình\s*bày|trinh\s*bay|sử\s*dụng\s*bảng|su\s*dung\s*bang|mermaid|mindmap|visual-first|"
            r"i\s*decided|i\s*will\s*present)",
            first_block,
            re.IGNORECASE,
        ):
            return blocks[1].strip() if len(blocks) > 1 else ""

        return text

    def _generate_answer_with_fallback(
        self,
        normalized_question: str,
        relevant_docs: list[Document],
    ) -> str:
        answer = self._llm_provider.generate_grounded_answer(normalized_question, relevant_docs).strip()
        if (not answer or self._is_fallback_answer(answer)) and self._backup_llm_provider is not None:
            logger.info("qa_primary_fallback_using_backup_provider")
            answer = self._backup_llm_provider.generate_grounded_answer(
                normalized_question,
                relevant_docs,
            ).strip()
        return answer

    def _normalize_mermaid_answer(self, answer: str) -> str:
        if not answer or "```" not in answer:
            return answer

        def _normalize_fenced_block(match: re.Match[str]) -> str:
            info_string = str(match.group(1) or "").strip().lower()
            block_text = str(match.group(2) or "")
            full_block = match.group(0)

            is_mermaid_candidate = (
                info_string.startswith("mermaid")
                or self._is_mermaid_like_block(block_text)
            )
            if not is_mermaid_candidate:
                return full_block

            normalized_block = self._normalize_mermaid_block_text(block_text)
            if not normalized_block:
                return full_block

            return f"```mermaid\n{normalized_block}\n```"

        return _FENCED_CODE_BLOCK_RE.sub(_normalize_fenced_block, answer)

    @staticmethod
    def _repair_mermaid_labeled_edges(block: str) -> str:
        def _pipe_replacement(match: re.Match[str]) -> str:
            edge = match.group(1)
            label = re.sub(r"\s+", " ", match.group(2)).strip()
            return f"{edge}|{label}| "

        repaired = _MERMAID_LABELED_EDGE_RE.sub(_pipe_replacement, block)
        repaired = _MERMAID_LABELED_EDGE_NO_PIPE_RE.sub(_pipe_replacement, repaired)
        repaired = _MERMAID_MERGED_EDGE_LINE_RE.sub(r"\1\n\3", repaired)
        return repaired

    def _filter_relevant_context(
        self,
        question: str,
        context_docs: list[Document],
    ) -> list[Document]:
        question_tokens = self._tokenize(question)
        if not question_tokens:
            return []

        relevant_docs: list[Document] = []
        for doc in context_docs:
            score = self._calculate_overlap_score(question_tokens, doc.page_content)
            if score < self._min_context_token_overlap:
                continue

            doc.metadata["relevance_score"] = round(score, 3)
            relevant_docs.append(doc)

        return relevant_docs

    def _retrieve_context_docs(
        self,
        raw_question: str,
        normalized_question: str,
        metadata_filter: dict[str, str | list[str]] | None,
        top_k: int,
    ) -> list[Document]:
        retrieval_started_at = time.perf_counter()
        queries = self._build_retrieval_queries(raw_question, normalized_question)
        if not queries:
            return []

        effective_filter = self._build_query_metadata_filter(raw_question, metadata_filter)
        retrieval_limit = max(top_k, min(top_k * 2, 24))
        search_k = retrieval_limit if not self._hybrid_retrieval_enabled else max(retrieval_limit, top_k * 2)

        aggregated: dict[str, dict[str, object]] = {}
        for query in queries:
            try:
                docs = self._vector_store_repository.similarity_search(
                    query=query,
                    k=search_k,
                    metadata_filter=effective_filter,
                )
            except Exception:
                logger.exception("qa_retrieval_query_failed query=%s", query[:120])
                docs = []

            self._accumulate_ranked_docs(aggregated, docs, source="vector")

            if self._hybrid_retrieval_enabled and hasattr(self._vector_store_repository, "keyword_search"):
                try:
                    keyword_docs = self._vector_store_repository.keyword_search(
                        query=query,
                        k=search_k,
                        metadata_filter=effective_filter,
                    )
                except Exception:
                    logger.exception("qa_keyword_query_failed query=%s", query[:120])
                    keyword_docs = []

                self._accumulate_ranked_docs(aggregated, keyword_docs, source="keyword")

        if not aggregated:
            if self._runtime_metrics is not None:
                retrieval_latency_ms = (time.perf_counter() - retrieval_started_at) * 1000.0
                self._runtime_metrics.record_pipeline_timing("retrieval_time_ms", retrieval_latency_ms)
            return []

        question_tokens = self._tokenize(raw_question)
        scored_documents: list[tuple[float, Document]] = []
        for payload in aggregated.values():
            doc = payload["doc"]
            if not isinstance(doc, Document):
                continue

            score = self._score_retrieval_payload(
                payload=payload,
                question_tokens=question_tokens,
                raw_question=raw_question,
                top_k=search_k,
            )
            doc.metadata["retrieval_score"] = round(score, 3)
            scored_documents.append((score, doc))

        scored_documents.sort(key=lambda item: item[0], reverse=True)
        ranked_docs = [doc for _, doc in scored_documents[:retrieval_limit]]

        reranking_latency_ms = 0.0
        if self._reranking_enabled:
            reranking_started_at = time.perf_counter()
            ranked_docs = self._rerank_documents(raw_question, ranked_docs, top_k)
            reranking_latency_ms = (time.perf_counter() - reranking_started_at) * 1000.0
            if self._runtime_metrics is not None:
                self._runtime_metrics.record_pipeline_timing("reranking_time_ms", reranking_latency_ms)

        compressed_docs = self._compress_context_docs(ranked_docs, retrieval_limit)
        retrieval_latency_ms = (time.perf_counter() - retrieval_started_at) * 1000.0

        if self._runtime_metrics is not None:
            self._runtime_metrics.record_pipeline_timing("retrieval_time_ms", retrieval_latency_ms)
            self._runtime_metrics.increment_counter("retrieval_candidates", len(scored_documents))
            self._runtime_metrics.increment_counter("retrieval_selected_chunks", len(compressed_docs))

        logger.info(
            "[Retrieval] hybrid=%s reranking=%s queries=%s candidates=%s selected=%s retrieval_ms=%.2f reranking_ms=%.2f",
            self._hybrid_retrieval_enabled,
            self._reranking_enabled,
            len(queries),
            len(scored_documents),
            len(compressed_docs),
            retrieval_latency_ms,
            reranking_latency_ms,
        )

        return compressed_docs

    def _accumulate_ranked_docs(
        self,
        aggregated: dict[str, dict[str, object]],
        docs: list[Document],
        source: str,
    ) -> None:
        hits_key = f"{source}_hits"
        rank_key = f"{source}_rank"

        for rank, doc in enumerate(docs):
            doc_key = self._document_key(doc)
            payload = aggregated.get(doc_key)
            if payload is None:
                payload = {
                    "doc": doc,
                    "vector_hits": 0,
                    "keyword_hits": 0,
                    "vector_rank": None,
                    "keyword_rank": None,
                    "keyword_score": 0.0,
                }
                aggregated[doc_key] = payload

            payload[hits_key] = int(payload.get(hits_key, 0)) + 1
            current_rank = payload.get(rank_key)
            if current_rank is None or rank < int(current_rank):
                payload[rank_key] = rank

            if source == "keyword":
                keyword_score = float(doc.metadata.get("keyword_score", 0.0) or 0.0)
                payload["keyword_score"] = max(float(payload.get("keyword_score", 0.0)), keyword_score)

    def _score_retrieval_payload(
        self,
        payload: dict[str, object],
        question_tokens: set[str],
        raw_question: str,
        top_k: int,
    ) -> float:
        doc = payload.get("doc")
        if not isinstance(doc, Document):
            return 0.0

        vector_rank_raw = payload.get("vector_rank")
        keyword_rank_raw = payload.get("keyword_rank")
        vector_hits = int(payload.get("vector_hits", 0))
        keyword_hits = int(payload.get("keyword_hits", 0))

        overlap_score = self._calculate_overlap_score(question_tokens, doc.page_content)
        vector_component = 0.0
        if vector_rank_raw is not None:
            vector_component = 1.0 - (float(vector_rank_raw) / max(1.0, float(top_k)))

        keyword_component = 0.0
        if keyword_rank_raw is not None:
            keyword_component = max(keyword_component, 1.0 - (float(keyword_rank_raw) / max(1.0, float(top_k))))
        keyword_component = max(
            keyword_component,
            min(1.0, float(payload.get("keyword_score", 0.0)) / 8.0),
        )

        hit_component = min(vector_hits + keyword_hits, 4) / 4
        metadata_boost = self._metadata_alignment_boost(raw_question, doc)
        quality_penalty = self._chunk_quality_penalty(raw_question, doc)

        final_score = (
            (overlap_score * 0.45)
            + (vector_component * 0.28)
            + (keyword_component * 0.17)
            + (hit_component * 0.10)
            + metadata_boost
            - quality_penalty
        )

        doc.metadata["metadata_boost"] = round(metadata_boost, 3)
        doc.metadata["quality_penalty"] = round(quality_penalty, 3)
        return max(0.0, final_score)

    def _build_query_metadata_filter(
        self,
        raw_question: str,
        metadata_filter: dict[str, str | list[str]] | None,
    ) -> dict[str, str | list[str]] | None:
        hinted_extensions = self._infer_extension_hints(raw_question)
        if not hinted_extensions:
            return metadata_filter

        merged_filter = dict(metadata_filter or {})
        current_extension = merged_filter.get("extension")
        if current_extension is None:
            merged_filter["extension"] = sorted(hinted_extensions)
            return merged_filter

        current_values = self._normalize_filter_values(current_extension)
        intersection = [value for value in current_values if value in hinted_extensions]
        if not intersection:
            return metadata_filter

        merged_filter["extension"] = intersection if len(intersection) > 1 else intersection[0]
        return merged_filter

    @staticmethod
    def _normalize_filter_values(value: str | list[str]) -> list[str]:
        values = value if isinstance(value, list) else [value]
        normalized: list[str] = []
        for item in values:
            normalized_value = str(item).lower().lstrip(".").strip()
            if not normalized_value:
                continue
            if normalized_value not in normalized:
                normalized.append(normalized_value)
        return normalized

    @staticmethod
    def _infer_extension_hints(raw_question: str) -> set[str]:
        question = raw_question.lower()
        hints: set[str] = set()

        if re.search(r"\b(slide|ppt|presentation)\b", question):
            hints.update({"ppt", "pptx"})

        # Restrict by spreadsheet extensions only when query explicitly indicates spreadsheet intent.
        # Generic requests like "tao bang so sanh" should not filter out PDF/DOCX/PPTX sources.
        if re.search(r"\b(sheet|spreadsheet|excel|xls|xlsx|csv)\b", question):
            hints.update({"xls", "xlsx", "csv"})

        if re.search(r"\b(section|chapter|heading|muc|mục|chuong|chương)\b", question):
            hints.update({"pdf", "doc", "docx", "md", "txt", "html", "htm"})

        if re.search(r"\b(image|figure|diagram|screenshot|chart|anh|ảnh|hinh|hình)\b", question):
            hints.update({"png", "jpg", "jpeg", "webp", "bmp", "pdf", "pptx", "docx"})

        if re.search(r"\b(json|field|schema|key|value|thuoc\s*tinh|thuộc\s*tính)\b", question):
            hints.update({"json"})

        if re.search(r"\b(xml|tag|node|attribute|xpath)\b", question):
            hints.update({"xml"})

        if re.search(r"\b(html|web|website|dom|heading|title)\b", question):
            hints.update({"html", "htm"})

        return hints

    def _metadata_alignment_boost(self, raw_question: str, doc: Document) -> float:
        question = raw_question.lower()
        metadata = doc.metadata
        extension = str(metadata.get("extension") or metadata.get("document_type") or "").lower().lstrip(".")
        content_type = str(metadata.get("content_type") or "").lower()

        boost = 0.0
        if re.search(r"\b(slide|ppt|presentation)\b", question):
            if extension in {"ppt", "pptx"} or metadata.get("slide_number") is not None:
                boost += 0.08

        if re.search(r"\b(sheet|excel|xlsx|csv|table|bang|bảng)\b", question):
            if extension in {"xls", "xlsx", "csv"} or metadata.get("sheet_name") is not None:
                boost += 0.08
            if content_type in {"csv_table", "spreadsheet_sheet"}:
                boost += 0.04
            if metadata.get("numeric_columns"):
                boost += 0.02

        if re.search(r"\b(section|chapter|heading|muc|mục|chuong|chương)\b", question):
            if metadata.get("section_title") or metadata.get("chapter") or metadata.get("heading"):
                boost += 0.05

        if re.search(r"\b(image|figure|diagram|screenshot|chart|anh|ảnh|hinh|hình)\b", question):
            if extension in {"png", "jpg", "jpeg", "bmp", "webp"}:
                boost += 0.06
            if metadata.get("ocr_applied") or metadata.get("image_analysis_applied"):
                boost += 0.04
            if content_type in {"image_document"}:
                boost += 0.04

        if re.search(r"\b(json|schema|field|key|value|thuoc\s*tinh|thuộc\s*tính)\b", question):
            if extension == "json" or content_type == "json_hierarchy":
                boost += 0.08

        if re.search(r"\b(xml|tag|node|attribute|xpath)\b", question):
            if extension == "xml" or content_type == "xml_hierarchy":
                boost += 0.08

        if re.search(r"\b(html|web|website|dom|title|heading)\b", question):
            if extension in {"html", "htm"} or content_type == "html_semantic":
                boost += 0.06

        return min(0.24, boost)

    def _chunk_quality_penalty(self, raw_question: str, doc: Document) -> float:
        metadata = doc.metadata
        content = str(doc.page_content or "")
        question = raw_question.lower()

        penalty = 0.0
        if _VISUAL_NOISE_TOKEN_RE.search(content):
            penalty += 0.12

        if metadata.get("image_content_unclear"):
            penalty += 0.14

        is_ocr_enriched = bool(metadata.get("ocr_applied")) or bool(metadata.get("image_analysis_applied"))
        if is_ocr_enriched:
            token_count = len(self._tokenize(content))
            if token_count < 6:
                penalty += 0.07
            if self._looks_like_noisy_chunk(content):
                penalty += 0.10

        if str(metadata.get("content_type") or "").lower() == "image_document":
            if not _IMAGE_QUESTION_HINT_RE.search(question):
                penalty += 0.05

        return min(0.32, penalty)

    @staticmethod
    def _looks_like_noisy_chunk(text: str) -> bool:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        if not lines:
            return True

        sample = " ".join(lines[:6])
        if len(sample) < 10:
            return True

        compact = [ch for ch in sample if not ch.isspace()]
        if not compact:
            return True

        meaningful_chars = sum(1 for ch in compact if _MEANINGFUL_TEXT_RE.search(ch))
        symbol_ratio = sum(1 for ch in compact if not ch.isalnum()) / len(compact)

        if symbol_ratio > 0.45 and (meaningful_chars / len(compact)) < 0.35:
            return True

        long_token_count = 0
        for token in sample.split():
            if len(token) < 22:
                continue
            vowel_count = sum(1 for ch in token.lower() if ch in "aeiou")
            if vowel_count <= 2:
                long_token_count += 1
        return long_token_count >= 2

    def _rerank_documents(self, raw_question: str, docs: list[Document], top_k: int) -> list[Document]:
        if len(docs) <= 1:
            return docs

        question_tokens = self._tokenize(raw_question)
        source_counts: dict[str, int] = {}
        section_counts: dict[str, int] = {}
        for doc in docs:
            source = str(doc.metadata.get("source", ""))
            section = str(doc.metadata.get("section_title") or doc.metadata.get("sheet_name") or "")
            source_counts[source] = source_counts.get(source, 0) + 1
            section_counts[section] = section_counts.get(section, 0) + 1

        scored: list[tuple[float, Document]] = []
        for index, doc in enumerate(docs):
            retrieval_score = float(doc.metadata.get("retrieval_score", 0.0))
            overlap_score = self._calculate_overlap_score(question_tokens, doc.page_content)
            source = str(doc.metadata.get("source", ""))
            section = str(doc.metadata.get("section_title") or doc.metadata.get("sheet_name") or "")

            cohesion = 0.0
            cohesion += min(0.08, max(0, source_counts.get(source, 0) - 1) * 0.02)
            cohesion += min(0.05, max(0, section_counts.get(section, 0) - 1) * 0.015)
            position_bias = 1.0 - (index / max(1, len(docs)))
            quality_penalty = self._chunk_quality_penalty(raw_question, doc)

            score = (
                (retrieval_score * 0.55)
                + (overlap_score * 0.32)
                + cohesion
                + (position_bias * 0.03)
                - (quality_penalty * 0.25)
            )
            doc.metadata["rerank_score"] = round(score, 3)
            scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        limit = max(top_k, min(top_k * 2, 24))
        return [doc for _, doc in scored[:limit]]

    def _compress_context_docs(self, docs: list[Document], max_docs: int) -> list[Document]:
        if not docs:
            return []

        deduplicated: list[Document] = []
        seen_hashes: set[str] = set()
        for doc in docs:
            normalized = self._normalize_text_query(re.sub(r"\s+", " ", doc.page_content))
            digest = hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            deduplicated.append(doc)

        compressed: list[Document] = []
        for doc in deduplicated:
            if not compressed:
                compressed.append(doc)
                continue

            previous = compressed[-1]
            if not self._can_merge_context_docs(previous, doc):
                compressed.append(doc)
                continue

            merged_content = f"{previous.page_content.strip()}\n{doc.page_content.strip()}".strip()
            if len(merged_content) > 2200:
                compressed.append(doc)
                continue

            merged_metadata = dict(previous.metadata)
            merged_metadata["merged_chunks"] = int(merged_metadata.get("merged_chunks", 1)) + 1
            compressed[-1] = Document(page_content=merged_content, metadata=merged_metadata)

        return compressed[:max_docs]

    @staticmethod
    def _can_merge_context_docs(previous: Document, current: Document) -> bool:
        previous_source = str(previous.metadata.get("source", ""))
        current_source = str(current.metadata.get("source", ""))
        if previous_source != current_source:
            return False

        previous_section = str(
            previous.metadata.get("section_title")
            or previous.metadata.get("sheet_name")
            or previous.metadata.get("slide_number")
            or ""
        )
        current_section = str(
            current.metadata.get("section_title")
            or current.metadata.get("sheet_name")
            or current.metadata.get("slide_number")
            or ""
        )
        return previous_section == current_section

    def _build_retrieval_queries(self, raw_question: str, normalized_question: str) -> list[str]:
        queries: list[str] = []
        seen: set[str] = set()

        def _add(query: str) -> None:
            clean_query = self._normalize_text_query(query)
            if not clean_query:
                return
            key = clean_query.lower()
            if key in seen:
                return
            seen.add(key)
            queries.append(clean_query)

        _add(raw_question)
        _add(normalized_question)

        if _IMAGE_QUESTION_HINT_RE.search(raw_question):
            # Add stable aliases to better recall chunks that were created from image understanding output.
            _add("image analysis visual chart diagram screenshot figure ocr")
            _add("phan tich hinh anh bieu do so do giao dien")

        for fragment in self._split_multi_part_question(raw_question):
            _add(fragment)

        focus_terms = self._extract_focus_terms(raw_question)
        if len(focus_terms) >= 3:
            _add(" ".join(focus_terms[:8]))

        if normalized_question != raw_question and len(focus_terms) >= 2:
            _add(f"{normalized_question}. {' '.join(focus_terms[:6])}")

        return queries

    def _resolve_effective_top_k(self, raw_question: str, top_k: int | None) -> int:
        base_top_k = top_k if top_k is not None else self._top_k
        token_count = len(self._tokenize(raw_question))
        bonus = 0

        if token_count >= 18:
            bonus += 2
        if token_count >= 30:
            bonus += 2
        if _COMPLEX_QUESTION_HINT_RE.search(raw_question):
            bonus += 2

        return max(1, min(20, base_top_k + bonus))

    @staticmethod
    def _split_multi_part_question(question: str) -> list[str]:
        if len(question) < 40:
            return []

        fragments: list[str] = []
        for fragment in re.split(r"[;\n?]+", question):
            clean_fragment = QuestionAnsweringService._normalize_text_query(fragment).strip(".,: -")
            if len(clean_fragment) < 16:
                continue
            if len(QuestionAnsweringService._tokenize(clean_fragment)) < 3:
                continue
            fragments.append(clean_fragment)

        return fragments[:4]

    @staticmethod
    def _extract_focus_terms(question: str) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()

        for token in re.findall(r"\w+", question.lower()):
            if len(token) <= 2:
                continue
            if token in _QUERY_EXPANSION_STOPWORDS:
                continue
            if token.isdigit():
                continue
            if token in seen:
                continue
            seen.add(token)
            terms.append(token)

        return terms

    @staticmethod
    def _document_key(doc: Document) -> str:
        source = str(doc.metadata.get("source", ""))
        page = str(doc.metadata.get("page", ""))
        chunk_index = str(doc.metadata.get("chunk_index", ""))
        start_index = str(doc.metadata.get("start_index", ""))
        content_hash = hashlib.sha1(
            doc.page_content[:512].encode("utf-8", errors="ignore")
        ).hexdigest()
        return "|".join([source, page, chunk_index, start_index, content_hash])

    @staticmethod
    def _calculate_overlap_score(question_tokens: set[str], context_text: str) -> float:
        context_tokens = QuestionAnsweringService._tokenize(context_text)
        if not context_tokens:
            return 0.0

        shared = len(question_tokens & context_tokens)
        return shared / max(1, len(question_tokens))

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"\w+", text)}

    @staticmethod
    def _is_fallback_answer(answer: str) -> bool:
        normalized = answer.strip().lower().rstrip(".")
        fallback = FALLBACK_ANSWER.strip().lower()
        return normalized == fallback

    @staticmethod
    def _extract_sources(context_docs: list[Document]) -> list[str]:
        unique_sources: list[str] = []
        seen: set[str] = set()

        for doc in context_docs:
            raw_source = str(doc.metadata.get("source", "unknown"))
            filename = Path(raw_source).name
            # Strip uuid prefix (e.g. "a1b2c3d4...hex_originalname.pdf" → "originalname.pdf")
            if "_" in filename and len(filename.split("_", 1)[0]) == 32:
                filename = filename.split("_", 1)[1]

            page = doc.metadata.get("page")
            chunk_index = doc.metadata.get("chunk_index")

            source_ref = filename
            if page is not None:
                source_ref += f" (trang {page})"
            if chunk_index is not None:
                source_ref += f" [đoạn {chunk_index}]"

            if source_ref in seen:
                continue

            seen.add(source_ref)
            unique_sources.append(source_ref)

        return unique_sources

    def _ensure_mindmap_answer(
        self,
        answer: str,
        context_docs: list[Document],
        normalized_question: str,
    ) -> str:
        selected_mindmap_block = self._select_mindmap_block(
            answer,
            context_docs,
            normalized_question,
        )
        cleaned_narrative = self._strip_mermaid_noise(answer)
        cleaned_narrative = self._normalize_markdown_table_blocks(cleaned_narrative)

        if selected_mindmap_block and cleaned_narrative:
            return f"{selected_mindmap_block}\n\n{cleaned_narrative}".strip()

        if selected_mindmap_block:
            return selected_mindmap_block

        return cleaned_narrative

    def _select_mindmap_block(
        self,
        answer: str,
        context_docs: list[Document],
        normalized_question: str,
    ) -> str:
        mermaid_blocks = self._extract_mermaid_blocks(answer)

        for mermaid_text in mermaid_blocks:
            normalized_block = self._normalize_mermaid_block_text(mermaid_text)
            if self._is_mermaid_mindmap(normalized_block) and self._has_sufficient_mindmap_branches(normalized_block):
                return self._wrap_mermaid_block(normalized_block)

        generated_mindmap_block = self._build_mindmap_block(answer, context_docs, normalized_question)
        if generated_mindmap_block:
            return generated_mindmap_block

        for mermaid_text in mermaid_blocks:
            normalized_block = self._normalize_mermaid_block_text(mermaid_text)
            if self._is_mermaid_mindmap(normalized_block):
                return self._wrap_mermaid_block(normalized_block)

        return ""

    def _strip_mermaid_noise(self, answer: str) -> str:
        if not answer:
            return ""

        without_fenced_mermaid = _MERMAID_BLOCK_RE.sub("", answer)
        without_mermaid_like_code_blocks = self._remove_mermaid_like_fenced_code_blocks(without_fenced_mermaid)
        without_unfenced_mermaid = self._remove_unfenced_mermaid_snippets(without_mermaid_like_code_blocks)
        without_lingering_mermaid = self._remove_lingering_mermaid_lines(without_unfenced_mermaid)
        compact = "\n".join(line.rstrip() for line in without_lingering_mermaid.splitlines()).strip()
        return re.sub(r"\n{3,}", "\n\n", compact)

    @staticmethod
    def _normalize_markdown_table_blocks(answer: str) -> str:
        if not answer:
            return ""

        lines = answer.splitlines()
        normalized_lines: list[str] = []
        index = 0

        while index < len(lines):
            line = lines[index].rstrip()
            if not _MARKDOWN_TABLE_ROW_RE.match(line):
                normalized_lines.append(line)
                index += 1
                continue

            table_block: list[str] = [line]
            next_index = index + 1
            while next_index < len(lines) and _MARKDOWN_TABLE_ROW_RE.match(lines[next_index].rstrip()):
                table_block.append(lines[next_index].rstrip())
                next_index += 1

            should_insert_separator = (
                len(table_block) >= 2
                and not _MARKDOWN_TABLE_SEPARATOR_RE.match(table_block[1])
            )
            if should_insert_separator:
                header_cells = QuestionAnsweringService._split_markdown_row_cells(table_block[0])
                if len(header_cells) >= 2:
                    normalized_lines.append(table_block[0].strip())
                    normalized_lines.append(
                        QuestionAnsweringService._build_markdown_separator_row(len(header_cells))
                    )
                    normalized_lines.extend(row.strip() for row in table_block[1:])
                else:
                    normalized_lines.extend(row.strip() for row in table_block)
            else:
                normalized_lines.extend(row.strip() for row in table_block)

            index = next_index

        compact = "\n".join(normalized_lines).strip()
        return re.sub(r"\n{3,}", "\n\n", compact)

    @staticmethod
    def _split_markdown_row_cells(row: str) -> list[str]:
        cleaned_row = row.strip().strip("|")
        if not cleaned_row:
            return []
        return [cell.strip() for cell in cleaned_row.split("|")]

    @staticmethod
    def _build_markdown_separator_row(column_count: int) -> str:
        safe_column_count = max(2, int(column_count))
        return "| " + " | ".join("---" for _ in range(safe_column_count)) + " |"

    @staticmethod
    def _remove_mermaid_like_fenced_code_blocks(answer: str) -> str:
        if not answer:
            return answer

        cleaned_lines: list[str] = []
        in_code_fence = False
        fence_header = ""
        fence_body: list[str] = []

        for raw_line in answer.splitlines():
            if not in_code_fence and _CODE_FENCE_LINE_RE.match(raw_line):
                in_code_fence = True
                fence_header = raw_line
                fence_body = []
                continue

            if in_code_fence:
                if _CODE_FENCE_LINE_RE.match(raw_line):
                    info_string = fence_header.strip()[3:].strip().lower()
                    block_text = "\n".join(fence_body).strip()
                    is_mermaid_like_block = (
                        info_string.startswith("mermaid")
                        or QuestionAnsweringService._is_mermaid_like_block(block_text)
                    )

                    if not is_mermaid_like_block:
                        cleaned_lines.append(fence_header)
                        cleaned_lines.extend(fence_body)
                        cleaned_lines.append(raw_line)

                    in_code_fence = False
                    fence_header = ""
                    fence_body = []
                    continue

                fence_body.append(raw_line)
                continue

            cleaned_lines.append(raw_line)

        if in_code_fence:
            # Keep unterminated fences unchanged to avoid dropping accidental user text.
            cleaned_lines.append(fence_header)
            cleaned_lines.extend(fence_body)

        return "\n".join(cleaned_lines)

    @staticmethod
    def _remove_lingering_mermaid_lines(answer: str) -> str:
        if not answer:
            return answer

        cleaned_lines: list[str] = []
        for raw_line in answer.splitlines():
            if QuestionAnsweringService._is_mermaid_like_line(raw_line):
                continue
            cleaned_lines.append(raw_line)

        return "\n".join(cleaned_lines)

    @staticmethod
    def _is_mermaid_like_block(block_text: str) -> bool:
        if not block_text:
            return False

        non_empty_lines = [line.strip() for line in block_text.splitlines() if line.strip()]
        if not non_empty_lines:
            return False

        if _MERMAID_DECLARATION_RE.match(non_empty_lines[0]):
            return True

        mermaid_like_lines = sum(
            1
            for line in non_empty_lines
            if QuestionAnsweringService._is_mermaid_like_line(line)
        )
        return mermaid_like_lines >= 2

    @staticmethod
    def _is_mermaid_like_line(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False

        if _MERMAID_DECLARATION_RE.match(stripped):
            return True
        if _MERMAID_EDGE_LINE_RE.match(stripped):
            return True
        if _MERMAID_NODE_LINE_RE.match(stripped):
            return True
        if _MERMAID_META_LINE_RE.match(stripped):
            return True
        if re.search(r"(?:-->|==>|-.->|---|~~>|<--|<==|<-.->)", stripped):
            return True
        if re.match(r"^[A-Za-z0-9_]+\s*$", stripped) and len(stripped) <= 4:
            return True

        return False

    @staticmethod
    def _remove_unfenced_mermaid_snippets(answer: str) -> str:
        if not answer:
            return answer

        cleaned_lines: list[str] = []
        in_code_fence = False
        in_unfenced_mermaid = False

        for raw_line in answer.splitlines():
            stripped = raw_line.strip()

            if _CODE_FENCE_LINE_RE.match(raw_line):
                in_code_fence = not in_code_fence
                in_unfenced_mermaid = False
                cleaned_lines.append(raw_line)
                continue

            if in_code_fence:
                cleaned_lines.append(raw_line)
                continue

            if _MERMAID_DECLARATION_RE.match(raw_line):
                in_unfenced_mermaid = True
                continue

            if in_unfenced_mermaid:
                if _BULLET_LINE_RE.match(stripped) or re.match(r"^#{1,6}\s+", stripped):
                    in_unfenced_mermaid = False
                    cleaned_lines.append(raw_line)
                    continue

                if not stripped or QuestionAnsweringService._is_mermaid_like_line(raw_line):
                    continue

                in_unfenced_mermaid = False
                cleaned_lines.append(raw_line)
                continue

            cleaned_lines.append(raw_line)

        compact = "\n".join(cleaned_lines).strip()
        return re.sub(r"\n{3,}", "\n\n", compact)

    @staticmethod
    def _normalize_mermaid_block_text(mermaid_text: str) -> str:
        repaired = QuestionAnsweringService._repair_mermaid_labeled_edges(mermaid_text)
        lines = repaired.splitlines()

        for index, raw_line in enumerate(lines):
            if not raw_line.strip():
                continue
            if raw_line.strip().lower().startswith("graph"):
                lines[index] = _MERMAID_GRAPH_DIRECTIVE_RE.sub(r"\1flowchart\2", raw_line, count=1)
            break

        normalized = "\n".join(lines).strip()
        return QuestionAnsweringService._ensure_mermaid_block_declaration(normalized)

    @staticmethod
    def _ensure_mermaid_block_declaration(mermaid_text: str) -> str:
        lines = [line.rstrip() for line in str(mermaid_text or "").splitlines()]
        non_empty_lines = [line for line in lines if line.strip()]
        if not non_empty_lines:
            return ""

        first_line = non_empty_lines[0].strip()
        if _MERMAID_DECLARATION_RE.match(first_line):
            return "\n".join(lines).strip()

        has_edge_or_node = any(
            _MERMAID_EDGE_LINE_RE.match(line)
            or _MERMAID_NODE_LINE_RE.match(line)
            for line in non_empty_lines
        )
        if not has_edge_or_node:
            return "\n".join(lines).strip()

        return "\n".join(["flowchart LR", *non_empty_lines]).strip()

    @staticmethod
    def _wrap_mermaid_block(mermaid_text: str) -> str:
        return f"```mermaid\n{mermaid_text.strip()}\n```"

    def _build_mindmap_block(
        self,
        answer: str,
        context_docs: list[Document],
        normalized_question: str,
    ) -> str:
        branches = self._collect_branches_from_answer(answer)

        if len(branches) < 4:
            for branch, children in self._collect_branches_from_context(context_docs).items():
                if branch not in branches:
                    branches[branch] = children
                if len(branches) >= 8:
                    break

        if len(branches) < 3:
            return ""

        root_label = self._derive_mindmap_root(normalized_question, context_docs)
        lines = [
            "```mermaid",
            "mindmap",
            f"  root(({root_label}))",
        ]

        for branch, children in list(branches.items())[:8]:
            branch_label = self._clean_mindmap_label(branch)
            if not branch_label:
                continue
            lines.append(f"    {branch_label}")
            for child in children[:4]:
                child_label = self._clean_mindmap_label(child)
                if child_label:
                    lines.append(f"      {child_label}")

        lines.append("```")
        return "\n".join(lines)

    def _collect_branches_from_answer(self, answer: str) -> OrderedDict[str, list[str]]:
        branches: OrderedDict[str, list[str]] = OrderedDict()
        text = _CODE_BLOCK_RE.sub("\n", answer)

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            bullet_match = _BULLET_LINE_RE.match(line)
            if bullet_match:
                content = bullet_match.group(1).strip()
            else:
                continue

            if self._is_noisy_visual_branch_line(content):
                continue

            branch, child = self._split_branch_child(content)
            self._append_branch(branches, branch, child)

            if len(branches) >= 8:
                break

        return branches

    def _collect_branches_from_context(self, context_docs: list[Document]) -> OrderedDict[str, list[str]]:
        branches: OrderedDict[str, list[str]] = OrderedDict()

        for doc in context_docs[:4]:
            for raw_line in doc.page_content.splitlines():
                line = raw_line.strip()
                if not line or len(line) < 3 or len(line) > 90:
                    continue

                if self._is_noisy_visual_branch_line(line):
                    continue

                if line.count("|") >= 2:
                    parts = [part.strip() for part in line.split("|") if part.strip()]
                    if len(parts) >= 2:
                        branch = parts[0]
                        if self._is_noisy_visual_branch_line(branch):
                            continue
                        for item in parts[1:3]:
                            if self._is_noisy_visual_branch_line(item):
                                continue
                            self._append_branch(branches, branch, item)
                    if len(branches) >= 8:
                        return branches
                    continue

                branch, child = self._split_branch_child(line)
                self._append_branch(branches, branch, child)
                if len(branches) >= 8:
                    return branches

        return branches

    @staticmethod
    def _split_branch_child(text: str) -> tuple[str, str | None]:
        cleaned = QuestionAnsweringService._clean_mindmap_label(text)
        if not cleaned:
            return "", None

        parts = re.split(r"\s*[:：]\s*", cleaned, maxsplit=1)
        if len(parts) == 2:
            branch = QuestionAnsweringService._clean_mindmap_label(parts[0])
            child = QuestionAnsweringService._clean_mindmap_label(parts[1])
            return branch, child or None

        return cleaned, None

    @staticmethod
    def _is_noisy_visual_branch_line(line: str) -> bool:
        normalized = str(line or "").strip()
        if not normalized:
            return True

        if _VISUAL_NOISE_LINE_RE.match(normalized):
            return True

        if _VISUAL_NOISE_TOKEN_RE.search(normalized):
            return True

        if normalized.startswith("[") and normalized.endswith("]"):
            return True

        if normalized.count("_") >= 2 and len(normalized.split()) <= 4:
            return True

        tokens = QuestionAnsweringService._tokenize(normalized)
        if len(tokens) <= 1 and len(normalized) <= 10:
            return True

        return False

    def _append_branch(
        self,
        branches: OrderedDict[str, list[str]],
        branch: str,
        child: str | None,
    ) -> None:
        branch_label = self._clean_mindmap_label(branch)
        if not branch_label:
            return

        if branch_label not in branches:
            branches[branch_label] = []

        if not child:
            return

        child_label = self._clean_mindmap_label(child)
        if not child_label or child_label == branch_label:
            return

        if child_label in branches[branch_label]:
            return

        if len(branches[branch_label]) >= 4:
            return

        branches[branch_label].append(child_label)

    @staticmethod
    def _derive_mindmap_root(normalized_question: str, context_docs: list[Document]) -> str:
        source_name = ""
        if context_docs:
            source_name = Path(str(context_docs[0].metadata.get("source", ""))).name
            if "_" in source_name and len(source_name.split("_", 1)[0]) == 32:
                source_name = source_name.split("_", 1)[1]

        if source_name:
            root = f"Mindmap {source_name}"
        elif normalized_question:
            root = f"Mindmap: {normalized_question[:60]}"
        else:
            root = "Mindmap tài liệu"

        return QuestionAnsweringService._clean_mindmap_label(root)

    @staticmethod
    def _extract_mermaid_block(answer: str) -> str | None:
        match = _MERMAID_BLOCK_RE.search(answer)
        if not match:
            return None
        return match.group(1).strip()

    @staticmethod
    def _extract_mermaid_blocks(answer: str) -> list[str]:
        return [match.group(1).strip() for match in _MERMAID_BLOCK_RE.finditer(answer)]

    @staticmethod
    def _is_mermaid_mindmap(mermaid_text: str) -> bool:
        for raw_line in mermaid_text.splitlines():
            line = raw_line.strip().lower()
            if not line:
                continue
            return line.startswith("mindmap")
        return False

    @staticmethod
    def _has_sufficient_mindmap_branches(mermaid_text: str) -> bool:
        top_level_branches: set[str] = set()
        for raw_line in mermaid_text.splitlines():
            if not raw_line.strip() or raw_line.strip().lower().startswith("mindmap"):
                continue

            if not re.match(r"^\s{4}\S", raw_line):
                continue

            branch = QuestionAnsweringService._clean_mindmap_label(raw_line.strip())
            if branch:
                top_level_branches.add(branch.lower())

        return len(top_level_branches) >= 3

    @staticmethod
    def _clean_mindmap_label(value: str) -> str:
        text = str(value or "")
        text = re.sub(r"[`\[\]{}<>|()\"'*!?~^]", " ", text)
        text = re.sub(r"[/\\]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip(" -:;,._\t")
        if len(text) > 64:
            text = text[:61].rstrip() + "..."
        return text

    @staticmethod
    def _is_mindmap_request(raw_question: str, normalized_question: str) -> bool:
        if _MINDMAP_REQUEST_RE.search(raw_question or ""):
            return True

        lowered = (normalized_question or "").lower()
        return "mindmap" in lowered or "sơ đồ tư duy" in lowered or "so do tu duy" in lowered

    @staticmethod
    def _normalize_text_query(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _normalize_question(question: str) -> str:
        candidate = QuestionAnsweringService._normalize_text_query(question)
        for pattern, replacement in _QUESTION_REWRITES:
            if pattern.match(candidate):
                return replacement
        return candidate
