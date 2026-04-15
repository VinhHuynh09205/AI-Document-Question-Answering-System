import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Iterator
from pathlib import Path

from app.models.entities import AnswerResult
from langchain_core.documents import Document
from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.interfaces.llm_provider import ILLMProvider
from app.services.interfaces.question_answering_service import IQuestionAnsweringService
from app.services.qa_constants import FALLBACK_ANSWER


logger = logging.getLogger(__name__)

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
        "Hãy tạo bảng so sánh các thông tin hoặc lựa chọn quan trọng xuất hiện trong tài liệu.",
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
        "Hãy tạo sơ đồ tư duy (mindmap) dạng text từ nội dung tài liệu, với chủ đề chính ở giữa và các nhánh con thể hiện ý phụ.",
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
    def _build_cache_key(question: str, metadata_filter: dict[str, str] | None, top_k: int) -> str:
        raw = json.dumps({"q": question, "f": metadata_filter or {}, "k": top_k}, sort_keys=True)
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
        metadata_filter: dict[str, str] | None = None,
        top_k: int | None = None,
    ) -> AnswerResult:
        effective_top_k = top_k if top_k is not None else self._top_k
        normalized_question = self._normalize_question(question)

        cache_key = self._build_cache_key(normalized_question, metadata_filter, effective_top_k)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.info("qa_cache_hit key=%s", cache_key[:12])
            return cached

        try:
            context_docs = self._vector_store_repository.similarity_search(
                query=normalized_question,
                k=effective_top_k,
                metadata_filter=metadata_filter,
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

        answer = self._llm_provider.generate_grounded_answer(normalized_question, relevant_docs).strip()
        if (not answer or self._is_fallback_answer(answer)) and self._backup_llm_provider is not None:
            logger.info("qa_primary_fallback_using_backup_provider")
            answer = self._backup_llm_provider.generate_grounded_answer(
                normalized_question,
                relevant_docs,
            ).strip()

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
        metadata_filter: dict[str, str] | None = None,
        top_k: int | None = None,
    ) -> Iterator[str]:
        effective_top_k = top_k if top_k is not None else self._top_k
        normalized_question = self._normalize_question(question)

        try:
            context_docs = self._vector_store_repository.similarity_search(
                query=normalized_question,
                k=effective_top_k,
                metadata_filter=metadata_filter,
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

        try:
            yield from self._llm_provider.stream_grounded_answer(normalized_question, relevant_docs)
        except Exception:
            logger.exception("qa_stream_llm_failed")
            yield FALLBACK_ANSWER

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

    @staticmethod
    def _normalize_question(question: str) -> str:
        candidate = question.strip()
        for pattern, replacement in _QUESTION_REWRITES:
            if pattern.match(candidate):
                return replacement
        return candidate
