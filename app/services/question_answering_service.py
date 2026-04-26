import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Iterator
from pathlib import Path

from langchain_core.documents import Document

from app.models.entities import AnswerResult
from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.interfaces.llm_provider import ILLMProvider
from app.services.interfaces.question_answering_service import IQuestionAnsweringService
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
    r"bang|bảng|chart|diagram|so\s*do|sơ\s*đồ|mindmap|truc\s*quan|trực\s*quan)",
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
_FLOWCHART_DIAGRAM_HINT_RE = re.compile(
    r"(quy\s*trinh|quy\s*trình|luong|luồng|flow|process|buoc|bước)",
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
        "Hãy tạo biểu đồ/sơ đồ trực quan bằng Mermaid trong khối ```mermaid``` (chọn loại phù hợp như flowchart, pie, timeline hoặc xychart), rồi giải thích ngắn 3-5 gạch đầu dòng.",
    ),
    (
        re.compile(
            r"(cau\s*hoi\s*trac\s*nghiem|câu\s*hỏi\s*trắc\s*nghiệm|quiz|multiple\s*choice|trac\s*nghiem|trắc\s*nghiệm)",
            re.IGNORECASE,
        ),
        "Hãy tạo 5-10 câu hỏi trắc nghiệm (4 đáp án A/B/C/D) từ nội dung tài liệu, kèm đáp án đúng và giải thích ngắn.",
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
        "Hãy dịch nội dung chính của tài liệu sang tiếng Anh, giữ nguyên ý nghĩa và cấu trúc.",
    ),
    (
        re.compile(
            r"(dich.*sang\s*tieng\s*viet|dịch.*sang\s*tiếng\s*việt|translate.*vietnamese)",
            re.IGNORECASE,
        ),
        "Hãy dịch nội dung chính của tài liệu sang tiếng Việt, giữ nguyên ý nghĩa và cấu trúc.",
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
        has_table = self._has_markdown_table(cleaned_answer)
        has_mermaid = self._extract_mermaid_block(cleaned_answer) is not None

        if not self._should_enrich_visual_answer(
            normalized_question,
            cleaned_answer,
            has_table=has_table,
            has_mermaid=has_mermaid,
        ):
            return cleaned_answer

        branches = self._collect_visual_branches(cleaned_answer, context_docs)

        additions: list[str] = []

        if not self._has_bullet_points(cleaned_answer):
            quick_summary = self._build_summary_bullets(branches)
            if quick_summary:
                additions.append(f"### Tóm tắt nhanh\n{quick_summary}")

        if not has_table:
            overview_table = self._build_overview_table(branches)
            if overview_table:
                additions.append(f"### Bảng tổng hợp\n{overview_table}")

        if not has_mermaid:
            overview_diagram = self._build_overview_diagram_block(
                branches,
                normalized_question,
                context_docs,
            )
            if overview_diagram:
                additions.append(f"### Sơ đồ tổng quan\n{overview_diagram}")

        if not additions:
            return cleaned_answer

        joined_additions = "\n\n".join(additions)
        return f"{cleaned_answer}\n\n{joined_additions}".strip()

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

    def _build_overview_diagram_block(
        self,
        branches: OrderedDict[str, list[str]],
        normalized_question: str,
        context_docs: list[Document],
    ) -> str:
        entries: list[tuple[str, list[str]]] = []
        for branch, children in list(branches.items())[:6]:
            branch_label = self._clean_mindmap_label(branch)
            if not branch_label:
                continue

            child_labels: list[str] = []
            for child in children[:2]:
                child_label = self._clean_mindmap_label(child)
                if child_label:
                    child_labels.append(child_label)

            entries.append((branch_label, child_labels))

        if len(entries) < 2:
            return ""

        root_label = self._derive_visual_root(normalized_question, context_docs)
        diagram_type = self._select_overview_diagram_type(normalized_question, entries)

        if diagram_type == "timeline":
            timeline_block = self._build_timeline_diagram_block(entries, root_label)
            if timeline_block:
                return timeline_block
        elif diagram_type == "pie":
            pie_block = self._build_pie_diagram_block(entries, root_label)
            if pie_block:
                return pie_block
        elif diagram_type == "mindmap":
            mindmap_block = self._build_visual_mindmap_diagram_block(entries, root_label)
            if mindmap_block:
                return mindmap_block

        return self._build_flowchart_diagram_block(entries, root_label)

    def _select_overview_diagram_type(
        self,
        normalized_question: str,
        entries: list[tuple[str, list[str]]],
    ) -> str:
        question_text = str(normalized_question or "").lower()

        if _TIMELINE_DIAGRAM_HINT_RE.search(question_text):
            return "timeline"
        if _PIE_DIAGRAM_HINT_RE.search(question_text):
            return "pie"
        if _MINDMAP_REQUEST_RE.search(question_text):
            return "mindmap"
        if _FLOWCHART_DIAGRAM_HINT_RE.search(question_text):
            return "flowchart"

        # Deterministic variation to avoid repetitive visuals for similar broad questions.
        fallback_types = ["flowchart", "mindmap", "timeline", "pie"]
        seed_source = question_text or " ".join(branch for branch, _ in entries)
        seed = int(hashlib.sha1(seed_source.encode("utf-8", errors="ignore")).hexdigest(), 16)
        return fallback_types[seed % len(fallback_types)]

    def _build_flowchart_diagram_block(
        self,
        entries: list[tuple[str, list[str]]],
        root_label: str,
    ) -> str:
        lines = [
            "```mermaid",
            "flowchart TD",
            f'  R["{self._escape_mermaid_label(root_label)}"]',
        ]

        for index, (branch_label, child_labels) in enumerate(entries, start=1):
            branch_id = f"B{index}"
            lines.append(
                f'  R --> {branch_id}["{self._escape_mermaid_label(branch_label)}"]'
            )
            for child_index, child_label in enumerate(child_labels, start=1):
                child_id = f"{branch_id}_{child_index}"
                lines.append(
                    f'  {branch_id} --> {child_id}["{self._escape_mermaid_label(child_label)}"]'
                )

        lines.append("```")
        return "\n".join(lines)

    def _build_visual_mindmap_diagram_block(
        self,
        entries: list[tuple[str, list[str]]],
        root_label: str,
    ) -> str:
        lines = [
            "```mermaid",
            "mindmap",
            f"  root(({self._clean_mindmap_label(root_label)}))",
        ]

        for branch_label, child_labels in entries:
            branch = self._clean_mindmap_label(branch_label)
            if not branch:
                continue

            lines.append(f"    {branch}")
            for child_label in child_labels:
                child = self._clean_mindmap_label(child_label)
                if child:
                    lines.append(f"      {child}")

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
        if not answer or "```mermaid" not in answer.lower():
            return answer

        def _normalize_block(match: re.Match[str]) -> str:
            block = self._repair_mermaid_labeled_edges(match.group(1))
            lines = block.splitlines()

            for index, raw_line in enumerate(lines):
                if not raw_line.strip():
                    continue

                if raw_line.strip().lower().startswith("graph"):
                    lines[index] = _MERMAID_GRAPH_DIRECTIVE_RE.sub(r"\1flowchart\2", raw_line, count=1)
                break

            normalized_block = "\n".join(lines).strip()
            return f"```mermaid\n{normalized_block}\n```"

        return _MERMAID_BLOCK_RE.sub(_normalize_block, answer)

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
        queries = self._build_retrieval_queries(raw_question, normalized_question)
        if not queries:
            return []

        aggregated: dict[str, dict[str, Document | int]] = {}
        for query in queries:
            try:
                docs = self._vector_store_repository.similarity_search(
                    query=query,
                    k=top_k,
                    metadata_filter=metadata_filter,
                )
            except Exception:
                logger.exception("qa_retrieval_query_failed query=%s", query[:120])
                continue

            for rank, doc in enumerate(docs):
                doc_key = self._document_key(doc)
                existing = aggregated.get(doc_key)
                if existing is None:
                    aggregated[doc_key] = {
                        "doc": doc,
                        "best_rank": rank,
                        "hits": 1,
                    }
                    continue

                existing["hits"] = int(existing["hits"]) + 1
                if rank < int(existing["best_rank"]):
                    existing["best_rank"] = rank

        if not aggregated:
            return []

        question_tokens = self._tokenize(raw_question)
        scored_documents: list[tuple[float, Document]] = []
        for payload in aggregated.values():
            doc = payload["doc"]
            if not isinstance(doc, Document):
                continue

            best_rank = int(payload["best_rank"])
            hits = int(payload["hits"])
            overlap_score = self._calculate_overlap_score(question_tokens, doc.page_content)
            rank_score = 1.0 - (best_rank / max(1, top_k))
            hit_score = min(hits, 3) / 3
            final_score = (overlap_score * 0.6) + (rank_score * 0.3) + (hit_score * 0.1)

            doc.metadata["retrieval_score"] = round(final_score, 3)
            scored_documents.append((final_score, doc))

        scored_documents.sort(key=lambda item: item[0], reverse=True)
        retrieval_limit = max(top_k, min(top_k * 2, 24))
        return [doc for _, doc in scored_documents[:retrieval_limit]]

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

        return "\n".join(lines).strip()

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

                if line.count("|") >= 2:
                    parts = [part.strip() for part in line.split("|") if part.strip()]
                    if len(parts) >= 2:
                        branch = parts[0]
                        for item in parts[1:3]:
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
