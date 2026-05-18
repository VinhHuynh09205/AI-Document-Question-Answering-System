from collections import OrderedDict

from langchain_core.documents import Document

from app.services.llm_providers.prompt_contract import (
    build_visual_first_human_prompt,
    build_visual_first_system_prompt,
)
from app.services.query_router import QueryRouter
from app.services.question_answering_service import QuestionAnsweringService
from app.services.qa_constants import FALLBACK_ANSWER


class FakeVectorStoreRepository:
    def __init__(
        self,
        docs_by_query: dict[str, list[Document]],
        keyword_docs_by_query: dict[str, list[Document]] | None = None,
        listed_docs: list[Document] | None = None,
    ) -> None:
        self._docs_by_query = docs_by_query
        self._keyword_docs_by_query = keyword_docs_by_query or {}
        self._listed_docs = listed_docs or []
        self.calls: list[tuple[str, int, dict[str, str | list[str]] | None]] = []
        self.keyword_calls: list[tuple[str, int, dict[str, str | list[str]] | None]] = []
        self.list_calls: list[tuple[dict[str, str | list[str]] | None, int | None]] = []

    def similarity_search(
        self,
        query: str,
        k: int,
        metadata_filter: dict[str, str | list[str]] | None = None,
    ) -> list[Document]:
        self.calls.append((query, k, metadata_filter))
        return list(self._docs_by_query.get(query, []))[:k]

    def keyword_search(
        self,
        query: str,
        k: int,
        metadata_filter: dict[str, str | list[str]] | None = None,
    ) -> list[Document]:
        self.keyword_calls.append((query, k, metadata_filter))
        return list(self._keyword_docs_by_query.get(query, []))[:k]

    def list_documents(
        self,
        metadata_filter: dict[str, str | list[str]] | None = None,
        limit: int | None = None,
    ) -> list[Document]:
        self.list_calls.append((metadata_filter, limit))
        docs = list(self._listed_docs)
        if metadata_filter:
            filtered_docs: list[Document] = []
            for doc in docs:
                matches = True
                for key, value in metadata_filter.items():
                    actual = str(doc.metadata.get(key) or "")
                    if isinstance(value, list):
                        if actual not in {str(item) for item in value}:
                            matches = False
                            break
                    elif actual != str(value):
                        matches = False
                        break
                if matches:
                    filtered_docs.append(doc)
            docs = filtered_docs
        if limit is not None:
            return docs[:limit]
        return docs


class FakeLLMProvider:
    def generate_grounded_answer(self, question: str, context_docs: list[Document]) -> str:
        joined_context = "\n".join(doc.page_content for doc in context_docs)
        return f"Q: {question}\n{joined_context}".strip()

    def stream_grounded_answer(self, question: str, context_docs: list[Document]):
        yield self.generate_grounded_answer(question, context_docs)


class AlwaysMissingLLMProvider:
    def generate_grounded_answer(self, question: str, context_docs: list[Document]) -> str:
        return "Không tìm thấy thông tin về mục được hỏi trong CONTEXT."

    def stream_grounded_answer(self, question: str, context_docs: list[Document]):
        yield self.generate_grounded_answer(question, context_docs)


class HallucinatedAcronymLLMProvider:
    def generate_grounded_answer(self, question: str, context_docs: list[Document]) -> str:
        return "Hệ thống hỏi đáp dựa trên kỹ thuật RAG (Relevance-Aware Graph) để giảm thiểu hallucination của AI model."

    def stream_grounded_answer(self, question: str, context_docs: list[Document]):
        yield self.generate_grounded_answer(question, context_docs)


class RawStructuredDumpLLMProvider:
    def generate_grounded_answer(self, question: str, context_docs: list[Document]) -> str:
        return (
            "Row 30 [A30:L30]: Ngày (A30): 2026-05-28 00:00:00; Khu vực (B30): Căn tin; "
            "Hoạt động (C30): Dọn vệ sinh khu vực; formula==IF(H30>=4.5,\"Rất tốt\",IF(H30>=4,\"Tốt\",\"Cần cải thiện\")) "
            "Row 12 [A12:L12]: Ngày (A12): 2026-05-10 00:00:00; Khu vực (B12): Thư viện; Hoạt động (C12): Đổi rác lấy cây."
        )

    def stream_grounded_answer(self, question: str, context_docs: list[Document]):
        yield self.generate_grounded_answer(question, context_docs)


class SheetSummaryDumpLLMProvider:
    def generate_grounded_answer(self, question: str, context_docs: list[Document]) -> str:
        return (
            "Sheet Index: 1\n"
            "Header Columns: Khoa, Số người tham gia, Chi phí(VND)\n"
            "Rows With Data: 120\n"
            "Detected Tables/Ranges: used_range_1"
        )

    def stream_grounded_answer(self, question: str, context_docs: list[Document]):
        yield self.generate_grounded_answer(question, context_docs)


class PoliteBulletSheetSummaryDumpLLMProvider:
    def generate_grounded_answer(self, question: str, context_docs: list[Document]) -> str:
        return (
            "Dạ, Sheet Index:1\n"
            "- Hidden Sheet:False\n"
            "- HeaderColumns: Ngày, Khu vực, Hoạt động, Chi phí(VND)\n"
            "- HeaderUnits: Chi phí(VND)=VND\n"
            "- RowsWithData:32\n"
            "- Tables/Ranges:1\n"
            "- used_range_1[used_range] A1:L32"
        )

    def stream_grounded_answer(self, question: str, context_docs: list[Document]):
        yield self.generate_grounded_answer(question, context_docs)


def test_complex_question_uses_query_expansion_and_keeps_relevant_context() -> None:
    raw_question = "So sanh dieu khoan thanh toan trong hop dong; danh gia rui ro cham giao hang?"

    doc_payment = Document(
        page_content="Dieu khoan thanh toan: ben mua thanh toan theo 3 dot trong 60 ngay.",
        metadata={"source": "payment.md", "chunk_index": 0},
    )
    doc_risk = Document(
        page_content="Rui ro cham giao hang: ben ban bi phat 5 phan tram gia tri hop dong.",
        metadata={"source": "risk.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={
            raw_question: [doc_payment],
            "So sanh dieu khoan thanh toan trong hop dong": [doc_payment],
            "danh gia rui ro cham giao hang": [doc_risk],
        }
    )

    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=4,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(raw_question)

    assert result.context_found is True
    assert "thanh toan" in result.answer.lower()
    assert "rui ro cham giao hang" in result.answer.lower()
    assert len(fake_repo.calls) >= 2


def test_secret_value_question_falls_back_instead_of_answering_from_loose_context() -> None:
    raw_question = "Mat khau admin la gi?"
    doc = Document(
        page_content="Admin co quyen quan ly nguoi dung va giam sat he thong.",
        metadata={"source": "security.md", "chunk_index": 0},
    )
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={raw_question: [doc]}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=4,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(raw_question)

    assert result.context_found is False
    assert result.answer == FALLBACK_ANSWER
    assert result.sources == []


def test_private_identifier_question_requires_direct_evidence() -> None:
    raw_question = "Tai lieu nao co ma so thue doanh nghiep?"
    doc = Document(
        page_content="Doanh nghiep co the so huu hang nghin file va tai lieu noi bo khac nhau.",
        metadata={"source": "rag.md", "chunk_index": 0},
    )
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={raw_question: [doc]}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=4,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(raw_question)

    assert result.context_found is False
    assert result.answer == FALLBACK_ANSWER


def test_explicit_model_page_question_requires_model_term_in_context() -> None:
    raw_question = "Test pdf.pdf co nhac chi tiet mo hinh YOLOv8 o trang nao?"
    doc = Document(
        page_content="Tai lieu noi ve thi giac may tinh, xu ly anh va cac ung dung thuc te.",
        metadata={"source": "Test pdf.pdf", "page": 3},
    )
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={raw_question: [doc]}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=4,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(raw_question)

    assert result.context_found is False
    assert result.answer == FALLBACK_ANSWER


def test_explicit_model_page_question_allows_grounded_term() -> None:
    raw_question = "Test pdf.pdf co nhac chi tiet mo hinh YOLOv8 o trang nao?"
    doc = Document(
        page_content="Trang 12 trinh bay chi tiet mo hinh YOLOv8 cho object detection.",
        metadata={"source": "Test pdf.pdf", "page": 12},
    )
    service = object.__new__(QuestionAnsweringService)

    assert service._try_build_missing_evidence_fallback(raw_question, [doc]) == ""


def test_complex_question_adapts_top_k_for_better_retrieval_coverage() -> None:
    raw_question = (
        "Hay phan tich chi tiet va so sanh cac dieu khoan thanh toan, thoi han giao hang, "
        "dieu kien phat cham tien do, va giai thich tai sao co the gay rui ro cho du an nay"
    )

    doc = Document(
        page_content="Du lieu hop dong mau cho phan tich.",
        metadata={"source": "contract.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={raw_question: [doc]})

    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    service.ask(raw_question)

    assert fake_repo.calls
    assert max(k for _, k, _ in fake_repo.calls) > 3


def test_document_scoped_context_rescue_uses_full_selected_document_when_retrieval_misses() -> None:
    question = "What is the refund period?"
    scoped_doc = Document(
        page_content="Refund policy: customers can request a refund within 30 days of purchase.",
        metadata={
            "source": "policy.pdf",
            "document_id": "doc-1",
            "extension": ".pdf",
            "section_title": "Refund policy",
        },
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={},
        listed_docs=[scoped_doc],
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "30 days" in result.answer
    assert fake_repo.list_calls


def test_metadata_alignment_boost_prefers_matching_section_path() -> None:
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    plain_doc = Document(
        page_content="Customers can submit a request within 30 days.",
        metadata={"source": "policy.docx", "extension": ".docx"},
    )
    structured_doc = Document(
        page_content="Customers can submit a request within 30 days.",
        metadata={
            "source": "policy.docx",
            "extension": ".docx",
            "section_path": "Policies > Refund policy",
            "structure_path": "Policies > Refund policy",
        },
    )

    plain_boost = service._metadata_alignment_boost("What is the refund policy?", plain_doc)
    structured_boost = service._metadata_alignment_boost("What is the refund policy?", structured_doc)

    assert structured_boost > plain_boost


def test_rank_scoped_context_docs_prefers_structure_match_when_content_ties() -> None:
    question = "What is the refund policy?"
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    generic_doc = Document(
        page_content="Customers can submit a request within 30 days.",
        metadata={
            "source": "policy.docx",
            "chunk_index": 1,
            "chunk_quality_score": 0.82,
        },
    )
    structured_doc = Document(
        page_content="Customers can submit a request within 30 days.",
        metadata={
            "source": "policy.docx",
            "chunk_index": 2,
            "chunk_quality_score": 0.82,
            "section_path": "Policies > Refund policy",
            "structure_path": "Policies > Refund policy",
        },
    )

    ranked_docs = service._rank_scoped_context_docs(
        raw_question=question,
        normalized_question=question,
        docs=[generic_doc, structured_doc],
        limit=2,
    )

    assert ranked_docs[0].metadata["chunk_index"] == 2


def test_raw_structured_dump_summary_is_rewritten_instead_of_leaking_rows() -> None:
    question = "Tài liệu nói gì về nội dung chính?"
    spreadsheet_doc = Document(
        page_content="Campaign spreadsheet summary",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
        },
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={question: [spreadsheet_doc]},
        listed_docs=[spreadsheet_doc],
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=RawStructuredDumpLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "row" not in result.answer.lower()
    assert "sheet index" not in result.answer.lower()
    assert "tài liệu dạng bảng" in result.answer.lower()


def test_hybrid_retrieval_uses_keyword_candidates_when_vector_misses() -> None:
    raw_question = "dieu khoan thanh toan cham tien do"
    keyword_doc = Document(
        page_content="Dieu khoan thanh toan cham tien do duoc quy dinh trong hop dong.",
        metadata={"source": "contract.md", "chunk_index": 0, "extension": "md"},
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={raw_question: []},
        keyword_docs_by_query={raw_question: [keyword_doc]},
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
        hybrid_retrieval_enabled=True,
        reranking_enabled=True,
    )

    result = service.ask(raw_question)

    assert result.context_found is True
    assert "thanh toan cham tien do" in result.answer.lower()
    assert fake_repo.keyword_calls


def test_query_metadata_hints_detect_slide_intent() -> None:
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    metadata_filter = service._build_query_metadata_filter(
        "Hay tom tat theo slide trong bai presentation nay",
        None,
    )

    assert metadata_filter is not None
    extensions = metadata_filter.get("extension")
    assert isinstance(extensions, list)
    assert "ppt" in extensions
    assert "pptx" in extensions


def test_query_metadata_hints_do_not_force_spreadsheet_for_generic_table_request() -> None:
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    metadata_filter = service._build_query_metadata_filter(
        "Tạo bảng so sánh",
        None,
    )

    assert metadata_filter is None


def test_query_metadata_hints_keep_spreadsheet_filter_for_explicit_excel_request() -> None:
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    metadata_filter = service._build_query_metadata_filter(
        "So sánh số liệu trong file excel",
        None,
    )

    assert metadata_filter is not None
    extensions = metadata_filter.get("extension")
    assert isinstance(extensions, list)
    assert "xlsx" in extensions
    assert "xls" in extensions


def test_query_metadata_hints_detect_sheet_reference_as_spreadsheet_intent() -> None:
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    metadata_filter = service._build_query_metadata_filter(
        "Ở Sheet1, thí sinh No.1 có tổng điểm và kết quả gì?",
        {"source": ["test.xlsx", "notes.md"]},
    )

    assert metadata_filter is not None
    assert metadata_filter.get("source") == ["test.xlsx", "notes.md"]
    extensions = metadata_filter.get("extension")
    assert isinstance(extensions, list)
    assert "xlsx" in extensions
    assert "xls" in extensions


def test_pptx_scoped_queries_expand_retrieval_window_for_cross_language_questions() -> None:
    question = "Người Nhật muốn làm việc cùng kiểu người nào?"
    docs = [
        Document(
            page_content=f"slide {index}: 日本人は、どんな人と一緒に仕事がしたいと考えていますか？",
            metadata={"source": "deck.pptx", "extension": ".pptx", "slide_number": index},
        )
        for index in range(1, 11)
    ]

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: docs})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
        hybrid_retrieval_enabled=True,
        reranking_enabled=True,
    )

    result = service.ask(question, metadata_filter={"source": "deck.pptx"})

    assert result.context_found is True
    assert "slide 10" in result.answer
    assert fake_repo.calls
    assert max(k for _, k, _ in fake_repo.calls) >= 32
    assert fake_repo.keyword_calls
    assert max(k for _, k, _ in fake_repo.keyword_calls) >= 32


def test_spreadsheet_row_lookup_returns_structured_answer_when_llm_misses() -> None:
    question = "Ở Sheet1, thí sinh No.1 có tổng điểm và kết quả gì?"
    row_doc = Document(
        page_content=(
            "File: Test.xlsx\n"
            "Sheet: Sheet1\n"
            "Row: 2\n"
            "No: 1\n"
            "Họ tên: Nguyễn Văn A\n"
            "Tổng điểm: 26\n"
            "Kết quả: Đậu\n"
        ),
        metadata={
            "source": "test.xlsx",
            "content_type": "spreadsheet_row",
            "sheet_name": "Sheet1",
            "row_index": 2,
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [row_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    normalized_answer = result.answer.lower()
    assert "không tìm thấy" not in normalized_answer
    assert "no.1" in normalized_answer
    assert "tổng điểm: 26" in normalized_answer
    assert "kết quả: đậu" in normalized_answer


def test_spreadsheet_row_lookup_supports_sheet_summary_sample_rows() -> None:
    question = "Ở Sheet1, thí sinh No.1 có tổng điểm và kết quả gì?"
    summary_doc = Document(
        page_content=(
            "File: Test.xlsx\n"
            "Sheet: Sheet1\n"
            "Columns: No, Họ tên, Tổng điểm, Kết quả\n"
            "Rows: 2\n"
            "Sample Rows:\n"
            "- Row 1: No: 1; Họ tên: Nguyễn Văn A; Tổng điểm: 26; Kết quả: Đậu\n"
            "- Row 2: No: 2; Họ tên: Nguyễn Văn B; Tổng điểm: 18; Kết quả: Rớt\n"
        ),
        metadata={
            "source": "test.xlsx",
            "content_type": "spreadsheet_sheet",
            "sheet_name": "Sheet1",
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [summary_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    normalized_answer = result.answer.lower()
    assert "no.1" in normalized_answer
    assert "tổng điểm: 26" in normalized_answer
    assert "kết quả: đậu" in normalized_answer


def test_spreadsheet_row_lookup_supports_japanese_score_and_result_labels() -> None:
    question = "Ở Sheet1, thí sinh No.1 có tổng điểm và kết quả gì?"
    row_doc = Document(
        page_content=(
            "File: Test.xlsx\n"
            "Sheet: Sheet1\n"
            "Row: 3\n"
            "No.: 1\n"
            "受験番号: KI2\n"
            "総計: 34\n"
            "結果: 合格\n"
        ),
        metadata={
            "source": "test.xlsx",
            "content_type": "spreadsheet_row",
            "sheet_name": "Sheet1",
            "row_index": 3,
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [row_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    normalized_answer = result.answer.lower()
    assert "no.1" in normalized_answer
    assert "34" in normalized_answer
    assert "合格" in result.answer


def test_spreadsheet_row_lookup_prefers_candidate_with_total_and_result_fields() -> None:
    question = "Ở Sheet1, thí sinh No.1 có tổng điểm và kết quả gì?"
    summary_doc = Document(
        page_content=(
            "File: Test.xlsx\n"
            "Sheet: Sheet1\n"
            "Columns: No., 受験番号, 氏名, 性別, 学科名, 日本語, 数学, 文学\n"
            "Rows: 2\n"
            "Sample Rows:\n"
            "- Row 1: No.: 1.0; 受験番号: KI2; 氏名: のび太 徳田; 性別: 男; 学科名: 教育学科; 日本語: 9.0; 数学: 8.5; 文学: 7.5\n"
        ),
        metadata={
            "source": "test.xlsx",
            "content_type": "spreadsheet_sheet",
            "sheet_name": "Sheet1",
        },
    )
    row_doc = Document(
        page_content=(
            "File: Test.xlsx\n"
            "Sheet: Sheet1\n"
            "Row: 3\n"
            "No.: 1.0\n"
            "受験番号: KI2\n"
            "氏名: のび太 徳田\n"
            "総計: 34\n"
            "結果: 合格\n"
        ),
        metadata={
            "source": "test.xlsx",
            "content_type": "spreadsheet_row",
            "sheet_name": "Sheet1",
            "row_index": 3,
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [summary_doc, row_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "34" in result.answer
    assert "合格" in result.answer


def test_spreadsheet_aggregate_sum_is_computed_from_structured_rows() -> None:
    question = "Trong sheet sales, tong revenue la bao nhieu?"
    table_doc = Document(
        page_content="Structured sales table",
        metadata={
            "source": "sales.xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Sales",
            "headers": ["Code", "Revenue"],
            "structured_rows": [
                {"row_number": 2, "values": {"Code": "A01", "Revenue": "100"}},
                {"row_number": 3, "values": {"Code": "A02", "Revenue": "150"}},
                {"row_number": 4, "values": {"Code": "A03", "Revenue": "200"}},
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [table_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "revenue" in result.answer.lower()
    assert "450" in result.answer


def test_spreadsheet_aggregate_sum_expands_to_full_document_scope() -> None:
    question = "Tong chi phi la bao nhieu?"
    retrieved_doc = Document(
        page_content="Retrieved spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {"row_number": 3, "values": {"Ngay": "2026-05-01", "Chi phí (VND)": "450000"}},
                {"row_number": 4, "values": {"Ngay": "2026-05-02", "Chi phí (VND)": "550000"}},
            ],
        },
    )
    additional_doc = Document(
        page_content="Additional spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {"row_number": 5, "values": {"Ngay": "2026-05-03", "Chi phí (VND)": "1000000"}},
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={question: [retrieved_doc]},
        listed_docs=[retrieved_doc, additional_doc],
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "2000000" in result.answer
    assert fake_repo.list_calls
    assert all(call == ({"document_id": "doc-1"}, None) for call in fake_repo.list_calls)


def test_spreadsheet_aggregate_max_returns_descriptor_value_from_full_document_scope() -> None:
    question = "Khu vực nào có số người tham gia cao nhất?"
    retrieved_doc = Document(
        page_content="Retrieved spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {
                    "row_number": 3,
                    "values": {
                        "Khu vực": "Ký túc xá",
                        "Số người tham gia": "32",
                    },
                },
            ],
        },
    )
    additional_doc = Document(
        page_content="Additional spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {
                    "row_number": 14,
                    "values": {
                        "Khu vực": "Thư viện",
                        "Số người tham gia": "95",
                    },
                },
                {
                    "row_number": 15,
                    "values": {
                        "Khu vực": "Giảng đường",
                        "Số người tham gia": "68",
                    },
                },
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={question: [retrieved_doc]},
        listed_docs=[retrieved_doc, additional_doc],
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "95" in result.answer
    assert "Thư viện" in result.answer
    assert "Khu vực" in result.answer


def test_spreadsheet_aggregate_supports_multi_token_sheet_hint_question() -> None:
    question = "ở sheet Du_lieu_chien_dich rác tái chế lớn nhất là bao nhiêu kg"
    table_doc = Document(
        page_content="Spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {
                    "row_number": 3,
                    "values": {
                        "Khu vực": "Ký túc xá",
                        "Rác tái chế (kg)": "4.1",
                    },
                },
                {
                    "row_number": 5,
                    "values": {
                        "Khu vực": "Thư viện",
                        "Rác tái chế (kg)": "12.2",
                    },
                },
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={question: [table_doc]},
        listed_docs=[table_doc],
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "12.2" in result.answer
    assert "Thư viện" in result.answer


def test_spreadsheet_structured_answer_uses_scoped_docs_when_retrieval_returns_nothing() -> None:
    question = "mức hài lòng lớn nhất là bao nhiêu"
    table_doc = Document(
        page_content="Spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {"row_number": 3, "values": {"Mức hài lòng": "4.6", "Khu vực": "Ký túc xá"}},
                {"row_number": 5, "values": {"Mức hài lòng": "4.9", "Khu vực": "Thư viện"}},
                {"row_number": 7, "values": {"Mức hài lòng": "3.8", "Khu vực": "Khoa CNTT"}},
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={},
        listed_docs=[table_doc],
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "4.9" in result.answer
    assert fake_repo.list_calls
    assert all(call == ({"document_id": "doc-1"}, None) for call in fake_repo.list_calls)


def test_spreadsheet_text_list_returns_all_distinct_activities_for_owner() -> None:
    question = "người phụ trách An có những hoạt động cụ thể nào"
    retrieved_doc = Document(
        page_content="Retrieved spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {
                    "row_number": 3,
                    "values": {
                        "Người phụ trách": "An",
                        "Hoạt động": "Đổi rác lấy cây",
                    },
                },
                {
                    "row_number": 13,
                    "values": {
                        "Người phụ trách": "An",
                        "Hoạt động": "Thu gom rác tái chế",
                    },
                },
            ],
        },
    )
    additional_doc = Document(
        page_content="Additional spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {
                    "row_number": 15,
                    "values": {
                        "Người phụ trách": "An",
                        "Hoạt động": "Dọn vệ sinh khu vực",
                    },
                },
                {
                    "row_number": 24,
                    "values": {
                        "Người phụ trách": "An",
                        "Hoạt động": "Workshop sống xanh",
                    },
                },
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={question: [retrieved_doc]},
        listed_docs=[retrieved_doc, additional_doc],
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "Đổi rác lấy cây" in result.answer
    assert "Thu gom rác tái chế" in result.answer
    assert "Dọn vệ sinh khu vực" in result.answer
    assert "Workshop sống xanh" in result.answer


def test_spreadsheet_text_count_counts_all_matching_rows_for_text_condition() -> None:
    question = "Có bao nhiêu đánh giá cần cải thiện"
    retrieved_doc = Document(
        page_content="Retrieved spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {"row_number": 3, "values": {"Đánh giá": "Cần cải thiện"}},
                {"row_number": 4, "values": {"Đánh giá": "Tốt"}},
            ],
        },
    )
    additional_doc = Document(
        page_content="Additional spreadsheet chunk",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {"row_number": 5, "values": {"Đánh giá": "Cần cải thiện"}},
                {"row_number": 6, "values": {"Đánh giá": "Cần cải thiện"}},
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={question: [retrieved_doc]},
        listed_docs=[retrieved_doc, additional_doc],
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "Có 3 đánh giá 'Cần cải thiện'" in result.answer
    assert "Row" not in result.answer


def test_spreadsheet_sheet_count_returns_direct_answer_from_sheet_metadata() -> None:
    question = "Có bao nhiêu sheet?"
    docs = [
        Document(
            page_content="File: campaign.xlsx\nSheet: Tong_quan\nSheet Index: 1\nHidden Sheet: False",
            metadata={
                "source": "campaign.xlsx",
                "content_type": "spreadsheet_sheet_summary",
                "sheet_name": "Tong_quan",
                "sheet_index": 1,
            },
        ),
        Document(
            page_content="File: campaign.xlsx\nSheet: Du_lieu_chien_dich\nSheet Index: 2\nHidden Sheet: False",
            metadata={
                "source": "campaign.xlsx",
                "content_type": "spreadsheet_sheet_summary",
                "sheet_name": "Du_lieu_chien_dich",
                "sheet_index": 2,
            },
        ),
    ]

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: docs})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "Tài liệu có 2 sheet" in result.answer
    assert "Tong_quan" in result.answer
    assert "Du_lieu_chien_dich" in result.answer


def test_spreadsheet_summary_request_rewrites_metadata_dump_to_narrative() -> None:
    question = "Tóm tắt toàn bộ tài liệu"
    docs = [
        Document(
            page_content=(
                "File: campaign.xlsx\n"
                "Sheet: Tong_quan\n"
                "Sheet Index: 1\n"
                "Header Columns: Khoa, Số người tham gia, Chi phí(VND)\n"
                "Rows With Data: 120"
            ),
            metadata={
                "source": "campaign.xlsx",
                "document_id": "doc-1",
                "content_type": "spreadsheet_sheet_summary",
                "sheet_name": "Tong_quan",
                "headers": ["Khoa", "Số người tham gia", "Chi phí(VND)"],
                "rows_with_data": 120,
            },
        )
    ]

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: docs}, listed_docs=docs)
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=SheetSummaryDumpLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "Sheet Index" not in result.answer
    assert "Header Columns" not in result.answer
    assert "các cột chính" in result.answer.lower()
    assert "tài liệu dạng bảng" in result.answer.lower()


def test_spreadsheet_summary_request_rewrites_polite_bullet_dump_to_narrative() -> None:
    question = "Tóm tắt toàn bộ tài liệu"
    docs = [
        Document(
            page_content=(
                "File: campaign.xlsx\n"
                "Sheet: Du_lieu_chien_dich\n"
                "Sheet Index: 1\n"
                "Header Columns: Ngày, Khu vực, Hoạt động, Chi phí(VND)\n"
                "Rows With Data: 32"
            ),
            metadata={
                "source": "campaign.xlsx",
                "document_id": "doc-1",
                "content_type": "spreadsheet_sheet_summary",
                "sheet_name": "Du_lieu_chien_dich",
                "headers": ["Ngày", "Khu vực", "Hoạt động", "Chi phí(VND)"],
                "rows_with_data": 32,
            },
        )
    ]

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: docs}, listed_docs=docs)
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=PoliteBulletSheetSummaryDumpLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "Sheet Index" not in result.answer
    assert "RowsWithData" not in result.answer
    assert "HeaderColumns" not in result.answer
    assert "tài liệu dạng bảng" in result.answer.lower()


def test_spreadsheet_filtered_value_answer_returns_numeric_value_for_named_group() -> None:
    question = "Số người tham gia của khoa CNTT là bao nhiêu?"
    table_doc = Document(
        page_content="Participation by group",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Tong_quan",
            "structured_rows": [
                {"row_number": 2, "values": {"Khoa": "CNTT", "Số người tham gia": "120", "Chi phí(VND)": "480000"}},
                {"row_number": 3, "values": {"Khoa": "Kinh tế", "Số người tham gia": "85", "Chi phí(VND)": "320000"}},
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(
        docs_by_query={question: [table_doc]},
        listed_docs=[table_doc],
    )
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question, metadata_filter={"document_id": "doc-1"})

    assert result.context_found is True
    assert "CNTT" in result.answer
    assert "120" in result.answer
    assert "Số người tham gia" in result.answer


def test_spreadsheet_date_lookup_returns_requested_column_from_matching_row() -> None:
    question = "Chi phí ngày 1/5/2026 là bao nhiêu?"
    table_doc = Document(
        page_content="Structured campaign table",
        metadata={
            "source": "campaign.xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "structured_rows": [
                {
                    "row_number": 2,
                    "values": {
                        "Ngày": "2026-05-01 00:00:00",
                        "Khu vực": "Thư viện",
                        "Chi phí(VND)": "480000",
                    },
                },
                {
                    "row_number": 3,
                    "values": {
                        "Ngày": "2026-05-03 00:00:00",
                        "Khu vực": "Ký túc xá",
                        "Chi phí(VND)": "450000",
                    },
                },
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [table_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "Du_lieu_chien_dich" in result.answer
    assert "Chi phí(VND): 480000" in result.answer


def test_table_query_group_by_sum_returns_grouped_totals_with_citations() -> None:
    question = "Tổng chi phí theo khu vực là bao nhiêu?"
    table_doc = Document(
        page_content="Campaign table",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Du_lieu_chien_dich",
            "table_name": "CampaignTable",
            "structured_rows": [
                {"row_number": 3, "values": {"Khu vực": "North", "Chi phí (VND)": "100000"}},
                {"row_number": 4, "values": {"Khu vực": "South", "Chi phí (VND)": "250000"}},
                {"row_number": 5, "values": {"Khu vực": "North", "Chi phí (VND)": "350000"}},
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [table_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "North: 450000" in result.answer
    assert "South: 250000" in result.answer
    assert "campaign.xlsx" in result.answer
    assert "Du_lieu_chien_dich" in result.answer


def test_table_query_top_rows_returns_ranked_rows_with_citations() -> None:
    question = "Top 2 khu vực có số người tham gia cao nhất là gì?"
    table_doc = Document(
        page_content="Participation table",
        metadata={
            "source": "campaign.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Tong_quan",
            "table_name": "ParticipationTable",
            "structured_rows": [
                {"row_number": 3, "values": {"Khu vực": "Thư viện", "Số người tham gia": "95"}},
                {"row_number": 4, "values": {"Khu vực": "Giảng đường", "Số người tham gia": "68"}},
                {"row_number": 5, "values": {"Khu vực": "Ký túc xá", "Số người tham gia": "32"}},
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [table_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "Top 2" in result.answer
    assert "Thư viện" in result.answer
    assert "95" in result.answer
    assert "Giảng đường" in result.answer
    assert "68" in result.answer
    assert "nguồn:" in result.answer


def test_table_query_compare_answer_aggregates_selected_values() -> None:
    question = "So sánh doanh thu giữa North và South"
    table_doc = Document(
        page_content="Revenue table",
        metadata={
            "source": "revenue.xlsx",
            "document_id": "doc-1",
            "extension": ".xlsx",
            "content_type": "spreadsheet_table_chunk",
            "sheet_name": "Sales",
            "table_name": "RevenueTable",
            "structured_rows": [
                {"row_number": 2, "values": {"Khu vực": "North", "Doanh thu": "100"}},
                {"row_number": 3, "values": {"Khu vực": "South", "Doanh thu": "80"}},
                {"row_number": 4, "values": {"Khu vực": "North", "Doanh thu": "50"}},
            ],
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [table_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "North: 150" in result.answer
    assert "South: 80" in result.answer
    assert "Chênh lệch: 70" in result.answer


def test_table_query_parses_pipe_table_for_ranked_docx_like_query() -> None:
    question = "Top 2 sản phẩm có doanh thu cao nhất là gì?"
    doc = Document(
        page_content="Sản phẩm | Doanh thu | Trạng thái\nA | 120 | Tốt\nB | 250 | Tốt\nC | 180 | Trễ",
        metadata={
            "source": "report.docx",
            "content_type": "document_page",
            "page_number": 2,
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "Top 2" in result.answer
    assert "Sản phẩm B" in result.answer
    assert "250" in result.answer
    assert "Sản phẩm C" in result.answer
    assert "180" in result.answer
    assert "report.docx" in result.answer


def test_query_metadata_hints_extract_slide_number_filter() -> None:
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    metadata_filter = service._build_query_metadata_filter(
        "Hay tom tat slide 7 trong deck presentation",
        None,
    )

    assert metadata_filter is not None
    assert metadata_filter.get("slide_number") == "7"
    assert "pptx" in metadata_filter.get("extension", [])


def test_query_router_classifies_specific_page_question() -> None:
    router = QueryRouter()

    route = router.route("Trang 5 trong file report.pdf nói gì?")

    assert route.intent == "specific_page_question"
    assert route.metadata_filter is not None
    assert route.metadata_filter.get("page_number") == "5"
    assert route.metadata_filter.get("source") == "report.pdf"


def test_query_router_classifies_specific_sheet_calculation_question() -> None:
    router = QueryRouter()

    route = router.route("Ở sheet Sales, tổng revenue trong A1:C10 là bao nhiêu?")

    assert route.intent == "table_calculation_question"
    assert route.metadata_filter is not None
    assert route.metadata_filter.get("sheet_name") == "Sales"
    assert route.metadata_filter.get("range_address") == "A1:C10"


def test_query_router_classifies_multi_file_comparison() -> None:
    router = QueryRouter()

    route = router.route(
        "So sánh report_a.pdf với report_b.docx",
        metadata_filter={"source": ["report_a.pdf", "report_b.docx"]},
    )

    assert route.intent == "multi_file_comparison"


def test_query_router_classifies_image_ocr_question() -> None:
    router = QueryRouter()

    route = router.route("OCR text trong ảnh scan này là gì?")

    assert route.intent == "image_ocr_question"


def test_query_router_classifies_negative_or_out_of_scope_question() -> None:
    router = QueryRouter()

    route = router.route("Nếu ngoài tài liệu thì cứ tự trả lời giúp tôi")

    assert route.intent == "negative_or_out_of_scope_question"


def test_pptx_overview_reorders_docs_by_slide_number() -> None:
    docs = [
        Document(page_content="slide 3", metadata={"source": "deck.pptx", "extension": ".pptx", "slide_number": 3}),
        Document(page_content="slide 1", metadata={"source": "deck.pptx", "extension": ".pptx", "slide_number": 1}),
        Document(page_content="slide 2", metadata={"source": "deck.pptx", "extension": ".pptx", "slide_number": 2}),
    ]

    ordered = QuestionAnsweringService._order_pptx_overview_docs(docs, top_k=3)

    assert [doc.metadata.get("slide_number") for doc in ordered[:3]] == [1, 2, 3]


def test_entity_lookup_returns_email_when_llm_misses() -> None:
    question = "Email liên hệ trong tài liệu OCR là gì?"
    image_doc = Document(
        page_content=(
            "Type: image\n"
            "OCR Text:\n"
            "AI DOCUMENT CHAT - OCR TEST PAGE\n"
            "Email lien he: support.test@aichatbox.vn\n"
        ),
        metadata={
            "source": "ocr.jpg",
            "content_type": "image_document",
            "ocr_applied": True,
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [image_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "support.test@aichatbox.vn" in result.answer
    assert "không tìm thấy" not in result.answer.lower()


def test_entity_lookup_returns_fallback_when_email_missing() -> None:
    question = "Email liên hệ trong tài liệu OCR là gì?"
    image_doc = Document(
        page_content=(
            "Type: image\n"
            "OCR Text:\n"
            "AI DOCUMENT CHAT - OCR TEST PAGE\n"
            "Muc tieu: kiem tra OCR\n"
        ),
        metadata={
            "source": "ocr.jpg",
            "content_type": "image_document",
            "ocr_applied": True,
        },
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [image_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is False
    assert result.answer == FALLBACK_ANSWER


def test_email_lookup_returns_extracted_email_when_present() -> None:
    question = "Email liên hệ trong tài liệu OCR là gì?"
    image_doc = Document(
        page_content=(
            "OCR Text:\n"
            "Lien he: support.team@example.com de duoc ho tro nhanh nhat.\n"
        ),
        metadata={"source": "ocr.jpg", "content_type": "image_document"},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [image_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "support.team@example.com" in result.answer


def test_email_lookup_supports_common_ocr_punctuation_noise() -> None:
    question = "Email liên hệ trong tài liệu OCR là gì?"
    image_doc = Document(
        page_content=(
            "OCR Text:\n"
            "Lien he: qa-team@example,com de duoc ho tro.\n"
        ),
        metadata={"source": "ocr.jpg", "content_type": "image_document"},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [image_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "qa-team@example.com" in result.answer


def test_email_lookup_returns_fallback_when_no_email_found() -> None:
    question = "Email liên hệ trong tài liệu OCR là gì?"
    image_doc = Document(
        page_content=(
            "OCR Text:\n"
            "Kiem tra trich xuat bang, ngay thang, email va so dien thoai.\n"
            "Khong co email cu the trong doan nay.\n"
        ),
        metadata={"source": "ocr.jpg", "content_type": "image_document"},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [image_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is False
    assert result.answer == FALLBACK_ANSWER


def test_website_lookup_returns_fallback_when_no_url_found() -> None:
    question = "Website trong tài liệu là gì?"
    image_doc = Document(
        page_content=(
            "OCR Text:\n"
            "Quan mo cua 07:00 - 22:00\n"
            "Wi-Fi: MayCoffee_Free\n"
        ),
        metadata={"source": "menu.png", "content_type": "image_document"},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [image_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is False
    assert result.answer == FALLBACK_ANSWER


def test_address_lookup_returns_fallback_when_no_address_found() -> None:
    question = "Trong file này có địa chỉ nhà riêng của thí sinh không?"
    row_doc = Document(
        page_content=(
            "File: Test.xlsx\n"
            "Sheet: Sheet1\n"
            "Row: 3\n"
            "No.: 1\n"
            "氏名: のび太 徳田\n"
            "総計: 34\n"
            "結果: 合格\n"
        ),
        metadata={"source": "test.xlsx", "content_type": "spreadsheet_row", "sheet_name": "Sheet1"},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [row_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is False
    assert result.answer == FALLBACK_ANSWER


def test_weekly_revenue_lookup_returns_highest_week_when_llm_misses() -> None:
    question = "Doanh thu tuần nào cao nhất?"
    image_doc = Document(
        page_content=(
            "Monthly Sales Summary 05/2026\n"
            "Week 1: 18\n"
            "Week 2: 20\n"
            "Week 3: 18.7\n"
            "Week 4: 22\n"
        ),
        metadata={"source": "sales.jpeg", "content_type": "image_document"},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [image_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "tuần 4" in result.answer.lower()
    assert "22" in result.answer


def test_weekly_revenue_lookup_handles_chart_style_lines_without_inline_week_value() -> None:
    question = "Doanh thu tuần nào cao nhất?"
    image_doc = Document(
        page_content=(
            "Monthly Sales Summary\n"
            "Doanh thu theo tuan (trieu dong)\n"
            "Trieu dong\n"
            "30\n"
            "25\n"
            "22\n"
            "20\n"
            "18\n"
            "Tuan 1\n"
            "Tuan 2\n"
            "Tuan 3\n"
            "Tuan 4\n"
            "Tuan 4 dat doanh thu cao nhat.\n"
            "Kenh ban hang\n"
        ),
        metadata={"source": "sales.jpeg", "content_type": "image_document"},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [image_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "tuần 4" in result.answer.lower()
    assert "22" in result.answer


def test_weekly_revenue_lookup_handles_split_highest_hint_lines() -> None:
    question = "Doanh thu tuần nào cao nhất?"
    image_doc = Document(
        page_content=(
            "Monthly Sales Summary\n"
            "Doanh thu theo tuan (trieu dong)\n"
            "30\n"
            "25\n"
            "22\n"
            "20\n"
            "18\n"
            "Tuan 1\n"
            "Tuan 2\n"
            "Tuan 3\n"
            "Tuan 4\n"
            "Tuan 4 dat doanh thu\n"
            "cao nhat.\n"
            "Kenh ban hang\n"
        ),
        metadata={"source": "sales.jpeg", "content_type": "image_document"},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [image_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "tuần 4" in result.answer.lower()
    assert "22" in result.answer


def test_llm_not_found_phrase_is_normalized_to_canonical_fallback() -> None:
    question = "Website liên hệ là gì?"
    generic_doc = Document(
        page_content="Tai lieu noi ve quy trinh noi bo, khong de cap website.",
        metadata={"source": "policy.md", "content_type": "text"},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [generic_doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=AlwaysMissingLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is False
    assert result.answer == FALLBACK_ANSWER


def test_context_compression_merges_adjacent_chunks_from_same_section() -> None:
    service = QuestionAnsweringService(
        vector_store_repository=FakeVectorStoreRepository(docs_by_query={}),
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    docs = [
        Document(
            page_content="Muc tieu quy 1 la tang truong doanh thu.",
            metadata={"source": "plan.md", "section_title": "Q1"},
        ),
        Document(
            page_content="Ke hoach thuc thi bao gom 3 giai doan.",
            metadata={"source": "plan.md", "section_title": "Q1"},
        ),
    ]

    compressed = service._compress_context_docs(docs, max_docs=5)

    assert len(compressed) == 1
    assert "3 giai doan" in compressed[0].page_content
    assert compressed[0].metadata.get("merged_chunks") == 2


def test_mermaid_labeled_edges_are_normalized_to_valid_syntax() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    raw_answer = (
        "```mermaid\n"
        "graph LR\n"
        "A[Giới tính] --> |Nam|> B[1]\n"
        "A --> |Nữ|> C[2]\n"
        "```"
    )

    normalized = service._normalize_mermaid_answer(raw_answer)

    assert "flowchart LR" in normalized
    assert "|Nam|>" not in normalized
    assert "|Nữ|>" not in normalized
    assert "A[Giới tính] -->|Nam| B[1]" in normalized
    assert "A -->|Nữ| C[2]" in normalized
    assert "B[1]\nA -->|Nữ| C[2]" in normalized


def test_mindmap_block_is_rebuilt_when_root_and_node_are_on_same_line() -> None:
    doc = Document(
        page_content=(
            "平均点: 7.5\n"
            "最高点: 9.0\n"
            "最低点: 5.0\n"
            "合格者数: 男 3 女 2\n"
            "合格率: 0.6"
        ),
        metadata={"source": "02-Traon Thao x Hoang Anh (5).xlsx", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    malformed_answer = (
        "```mermaid\n"
        "mindmap\n"
        "  root((*Mindmap 02-Traon Thao x Hoang Anh (5).xlsx)) 平均点\n"
        "    ?\n"
        "    最高点\n"
        "```"
    )

    rebuilt = service._ensure_mindmap_answer(
        malformed_answer,
        context_docs=[doc],
        normalized_question="tao mindmap tai lieu",
    )

    assert "```mermaid\nmindmap" in rebuilt
    assert ")) 平均点" not in rebuilt
    assert "  root((" in rebuilt
    assert "平均点" in rebuilt
    assert "最高点" in rebuilt


def test_mermaid_repairs_no_pipe_labels_and_merged_edge_lines() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    raw_answer = (
        "```mermaid\n"
        "graph LR\n"
        "A -->Nhật ngữ học> B[5 học sinh] A -->|Nữ|> C[2]\n"
        "```"
    )

    normalized = service._normalize_mermaid_answer(raw_answer)

    assert "flowchart LR" in normalized
    assert "-->Nhật ngữ học>" not in normalized
    assert "|Nữ|>" not in normalized
    assert "A -->|Nhật ngữ học| B[5 học sinh]" in normalized
    assert "B[5 học sinh]\nA -->|Nữ| C[2]" in normalized


def test_normalize_mermaid_answer_promotes_unlabeled_mermaid_code_fence() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    raw_answer = (
        "```\n"
        "A -->|Đáng tin| B[Được cung cấp từ nguồn chính thức]\n"
        "B -->|Cần lưu ý| C[Thông tin có thể không cập nhật]\n"
        "```"
    )

    normalized = service._normalize_mermaid_answer(raw_answer)

    assert normalized.startswith("```mermaid")
    assert "flowchart LR" in normalized
    assert "A -->|Đáng tin| B[Được cung cấp từ nguồn chính thức]" in normalized


def test_normalize_mermaid_answer_adds_declaration_when_missing() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    raw_answer = (
        "```mermaid\n"
        "A --> B[Buoc 1]\n"
        "B --> C[Buoc 2]\n"
        "```"
    )

    normalized = service._normalize_mermaid_answer(raw_answer)

    assert "```mermaid\nflowchart LR" in normalized
    assert "A --> B[Buoc 1]" in normalized
    assert "B --> C[Buoc 2]" in normalized


def test_normalize_mermaid_answer_does_not_touch_non_mermaid_code_fence() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    raw_answer = "```python\nprint('hello')\n```"
    normalized = service._normalize_mermaid_answer(raw_answer)

    assert normalized == raw_answer


def test_ensure_mindmap_answer_strips_unfenced_mermaid_noise() -> None:
    doc = Document(
        page_content="Chu de: Nhat ngu\nMuc tieu: JLPT\nLo trinh: Co ban\nTu vung: N5\n",
        metadata={"source": "mindmap-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    noisy_answer = (
        "```mermaid\n"
        "mindmap\n"
        "  root((Mindmap tai lieu))\n"
        "    Nhanh 1\n"
        "    Nhanh 2\n"
        "    Nhanh 3\n"
        "```\n\n"
        "Flowchart LR\n"
        "A-->B\n"
        "B-->C\n\n"
        "- Y chinh: giu lai phan mo ta.\n"
    )

    cleaned = service._ensure_mindmap_answer(
        noisy_answer,
        context_docs=[doc],
        normalized_question="tao mindmap tai lieu",
    )

    assert "```mermaid" in cleaned
    assert "Flowchart LR" not in cleaned
    assert "A-->B" not in cleaned
    assert "B-->C" not in cleaned
    assert "- Y chinh: giu lai phan mo ta." in cleaned


def test_ensure_mindmap_answer_keeps_text_when_only_unfenced_mermaid_present() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    noisy_answer = (
        "Flowchart LR\n"
        "A-->B\n"
        "B-->C\n"
        "Noi dung mo ta can giu lai\n"
    )

    cleaned = service._ensure_mindmap_answer(
        noisy_answer,
        context_docs=[],
        normalized_question="tao mindmap",
    )

    assert "Flowchart LR" not in cleaned
    assert "A-->B" not in cleaned
    assert "B-->C" not in cleaned
    assert "Noi dung mo ta can giu lai" in cleaned


def test_ensure_mindmap_answer_keeps_single_mindmap_and_strips_extra_mermaid_blocks() -> None:
    doc = Document(
        page_content="Chu de: Nhat ngu\nMuc tieu: JLPT\nLo trinh: Co ban\n",
        metadata={"source": "mindmap-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    noisy_answer = (
        "```mermaid\n"
        "mindmap\n"
        "  root((Mindmap tai lieu))\n"
        "    Nhanh 1\n"
        "    Nhanh 2\n"
        "    Nhanh 3\n"
        "```\n\n"
        "```\n"
        "Flowchart LR\n"
        "A-->B\n"
        "B-->C\n"
        "```\n\n"
        "Noi dung mo ta can giu lai\n"
    )

    cleaned = service._ensure_mindmap_answer(
        noisy_answer,
        context_docs=[doc],
        normalized_question="tao mindmap",
    )

    assert cleaned.count("```mermaid") == 1
    assert "Flowchart LR" not in cleaned
    assert "A-->B" not in cleaned
    assert "B-->C" not in cleaned
    assert "Noi dung mo ta can giu lai" in cleaned


def test_ensure_mindmap_answer_prefers_valid_existing_mindmap_over_invalid_one() -> None:
    doc = Document(
        page_content="Chu de: Nhat ngu\nMuc tieu: JLPT\nLo trinh: Co ban\n",
        metadata={"source": "mindmap-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    noisy_answer = (
        "```mermaid\n"
        "mindmap\n"
        "  root((Invalid))\n"
        "    only one branch\n"
        "```\n\n"
        "```mermaid\n"
        "mindmap\n"
        "  root((Valid root))\n"
        "    Nhanh 1\n"
        "    Nhanh 2\n"
        "    Nhanh 3\n"
        "```\n"
    )

    cleaned = service._ensure_mindmap_answer(
        noisy_answer,
        context_docs=[doc],
        normalized_question="tao mindmap",
    )

    assert cleaned.count("```mermaid") == 1
    assert "Valid root" in cleaned
    assert "only one branch" not in cleaned


def test_ensure_mindmap_answer_normalizes_markdown_table_without_separator() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    noisy_answer = (
        "```mermaid\n"
        "mindmap\n"
        "  root((Mindmap SMD))\n"
        "    Tinh nang\n"
        "    Gioi han\n"
        "    AI\n"
        "```\n\n"
        "Duoi day la cac tinh nang chinh:\n"
        "| Tinh nang | Mo ta |\n"
        "| Quan ly vong doi syllabus | Quan ly tu soan thao den cong bo |\n"
        "| Ho tro workflow phe duyet da cap | Giang vien den hieu truong |\n"
    )

    cleaned = service._ensure_mindmap_answer(
        noisy_answer,
        context_docs=[],
        normalized_question="tao mindmap",
    )

    assert "```mermaid" in cleaned
    assert "| Tinh nang | Mo ta |" in cleaned
    assert "| --- | --- |" in cleaned
    assert "| Quan ly vong doi syllabus | Quan ly tu soan thao den cong bo |" in cleaned


def test_ensure_visual_answer_prefers_text_and_mindmap_for_overview_detail_question() -> None:
    doc = Document(
        page_content=(
            "Muc tieu: Ho tro hoc vien\n"
            "Phuong phap: On tap theo chu de\n"
            "Ket qua: Cai thien diem so\n"
        ),
        metadata={"source": "visual-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    answer = "Noi dung tong quan ve tai lieu."
    enriched = service._ensure_visual_answer(
        answer,
        context_docs=[doc],
        normalized_question="phan tich tong quan",
    )

    assert "Noi dung tong quan ve tai lieu." in enriched
    assert "### Tóm tắt nhanh" in enriched
    assert "### Bảng tổng hợp" not in enriched
    assert "### Mindmap chủ đề" in enriched
    assert "```mermaid\nmindmap" in enriched


def test_ensure_visual_answer_combines_table_and_flowchart_for_process_comparison_question() -> None:
    doc = Document(
        page_content=(
            "Buoc 1: Tiep nhan yeu cau\n"
            "Buoc 2: Phan loai va danh gia\n"
            "Buoc 3: Thuc hien xu ly\n"
            "Buoc 4: Kiem tra ket qua\n"
        ),
        metadata={"source": "workflow-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    enriched = service._ensure_visual_answer(
        "Day la quy trinh xu ly va can doi chieu cac buoc.",
        context_docs=[doc],
        normalized_question="so sanh quy trinh xu ly",
    )

    assert "### Tóm tắt nhanh" not in enriched
    assert "### Bảng so sánh" in enriched
    assert "### Sơ đồ quy trình" in enriched
    assert "flowchart LR" in enriched


def test_visual_plan_prefers_table_for_comparison_question() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    branches = OrderedDict(
        {
            "Chi phi": ["Cao", "Toi uu ngan sach"],
            "Tien do": ["Nhanh", "Can giam sat"],
            "Rui ro": ["Trung binh", "Co phuong an du phong"],
            "Hieu qua": ["On dinh", "De mo rong"],
        }
    )

    add_summary, table_variant, mermaid_variant = service._build_visual_plan(
        "so sanh va danh gia cac nhom noi dung",
        branches,
    )

    assert add_summary is False
    assert table_variant == "matrix"
    assert mermaid_variant is None


def test_visual_plan_prefers_flowchart_for_sequential_content() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    branches = OrderedDict(
        {
            "Buoc 1": ["Khoi dong"],
            "Buoc 2": ["Xu ly"],
            "Buoc 3": ["Danh gia"],
        }
    )

    add_summary, table_variant, mermaid_variant = service._build_visual_plan(
        "lap lo trinh cac buoc thuc hien",
        branches,
    )

    assert add_summary is False
    assert table_variant is None
    assert mermaid_variant == "flowchart"


def test_visual_plan_prefers_mindmap_for_broad_topic_question() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    branches = OrderedDict(
        {
            "Nen tang": ["Frontend", "Backend", "Du lieu"],
            "Nguoi dung": ["Hoc vien", "Giang vien"],
            "Van hanh": ["Bao tri", "Giam sat"],
            "Bao mat": ["Phan quyen", "Nhat ky"],
            "Bao cao": ["Tong hop", "Phan tich"],
        }
    )

    add_summary, table_variant, mermaid_variant = service._build_visual_plan(
        "tong quan he thong va chu de chinh",
        branches,
    )

    assert add_summary is True
    assert table_variant is None
    assert mermaid_variant == "mindmap"


def test_table_heavy_answer_is_converted_to_text_first_with_single_support_table() -> None:
    doc = Document(
        page_content=(
            "Cong cu quan ly yeu cau | Luu tru thong tin | Kiem tra nhat quan\n"
            "Cong cu phan tich dong | Cap nhat bien | Xac dinh loi\n"
            "Cong cu quan ly test | Ke hoach | Bao cao\n"
        ),
        metadata={"source": "tools-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    answer = (
        "| Loai cong cu | Mo ta |\n"
        "|---|---|\n"
        "| Cong cu quan ly yeu cau | Luu tru thong tin yeu cau |\n"
        "| Cong cu phan tich dong | Cap nhat va su dung bien |\n\n"
        "| Loai cong cu | Mo ta |\n"
        "|---|---|\n"
        "| Cong cu quan ly test | Quan ly ke hoach test |\n"
        "| Cong cu do do bao phu | Do bao phu cac thanh phan |"
    )

    enriched = service._ensure_visual_answer(
        answer,
        context_docs=[doc],
        normalized_question="tom tat cac cong cu kiem thu phan mem",
    )

    assert enriched.startswith("Nội dung chính tập trung vào")
    assert enriched.count("### Bảng") == 0
    assert enriched.count("| Loai cong cu | Mo ta |") == 0


def test_ensure_visual_answer_keeps_simple_fact_response_concise() -> None:
    doc = Document(
        page_content="Dinh nghia: NLP la xu ly ngon ngu tu nhien.",
        metadata={"source": "fact-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    concise = service._ensure_visual_answer(
        "NLP la xu ly ngon ngu tu nhien.",
        context_docs=[doc],
        normalized_question="NLP la gi",
    )

    assert "### Bảng tổng hợp" not in concise
    assert "### Sơ đồ tổng quan" not in concise
    assert "```mermaid" not in concise


def test_simple_fact_intent_strips_existing_mermaid_and_table_artifacts() -> None:
    doc = Document(
        page_content="Dinh nghia: NLP la xu ly ngon ngu tu nhien.",
        metadata={"source": "fact-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    noisy_answer = (
        "NLP la xu ly ngon ngu tu nhien.\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "A --> B\n"
        "```\n\n"
        "| Cot A | Cot B |\n"
        "|---|---|\n"
        "| x | y |\n"
    )

    concise = service._ensure_visual_answer(
        noisy_answer,
        context_docs=[doc],
        normalized_question="NLP la gi",
    )

    assert "NLP la xu ly ngon ngu tu nhien." in concise
    assert "```mermaid" not in concise
    assert "flowchart LR" not in concise
    assert "|---|---|" not in concise


def test_ensure_visual_answer_skips_translation_requests() -> None:
    doc = Document(
        page_content="Software testing helps detect defects early in the lifecycle.",
        metadata={"source": "translate-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    translated = service._ensure_visual_answer(
        "Software testing helps detect defects early in the lifecycle.",
        context_docs=[doc],
        normalized_question="Hãy dịch nội dung chính của tài liệu sang tiếng Anh. Chỉ trả về bản dịch tiếng Anh, không thêm tiếng Việt, không tóm tắt, không bảng Markdown, không Mermaid, không giải thích, không mô tả quyết định trình bày.",
    )

    assert translated == "Software testing helps detect defects early in the lifecycle."


def test_transform_intent_strips_existing_mermaid_and_tables_from_answer() -> None:
    doc = Document(
        page_content="Software testing helps detect defects early in the lifecycle.",
        metadata={"source": "translate-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    noisy_answer = (
        "Software testing helps detect defects early in the lifecycle.\n\n"
        "### So do quy trinh\n"
        "```mermaid\n"
        "flowchart LR\n"
        "A --> B\n"
        "```\n\n"
        "| Step | Value |\n"
        "|---|---|\n"
        "| Analyze | Input |\n"
    )

    cleaned = service._ensure_visual_answer(
        noisy_answer,
        context_docs=[doc],
        normalized_question="dich sang tieng anh",
    )

    assert "Software testing helps detect defects early in the lifecycle." in cleaned
    assert "```mermaid" not in cleaned
    assert "flowchart LR" not in cleaned
    assert "|---|---|" not in cleaned
    assert "### So do quy trinh" not in cleaned


def test_should_skip_visual_enrichment_for_transform_and_format_intents() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    transform_questions = [
        "dich sang tieng anh",
        "tao quiz tu noi dung",
        "lam slide thuyet trinh",
        "viet lai theo van phong hoc thuat",
        "dinh nghia NLP la gi",
    ]

    for question in transform_questions:
        assert service._should_enrich_visual_answer(
            question,
            answer="Noi dung tra loi giu nguyen theo tac vu.",
            has_table=False,
            has_mermaid=False,
        ) is False


def test_strip_presentation_meta_removes_format_narration() -> None:
    cleaned = QuestionAnsweringService._strip_presentation_meta(
        "Dựa trên nội dung của tài liệu, tôi quyết định trình bày bằng bảng Markdown để dễ theo dõi.\n\nThis is the actual answer."
    )

    assert cleaned == "This is the actual answer."


def test_sanitize_context_references_removes_prompt_echo_prefix() -> None:
    cleaned = QuestionAnsweringService._sanitize_context_references(
        "Trả lời câu hỏi dựa trên CONTEXT:\n\nSlide 6 là slide mô tả kiến trúc tổng thể của hệ thống."
    )

    assert cleaned == "Slide 6 là slide mô tả kiến trúc tổng thể của hệ thống."


def test_sanitize_context_references_rewrites_context_to_tai_lieu() -> None:
    cleaned = QuestionAnsweringService._sanitize_context_references(
        "Thông điệp về khác biệt văn hóa trong CONTEXT này không rõ ràng và cụ thể."
    )

    assert "CONTEXT" not in cleaned
    assert cleaned == "Thông điệp về khác biệt văn hóa trong tài liệu này không rõ ràng và cụ thể."


def test_sanitize_unverified_acronym_expansions_removes_ungrounded_expansion() -> None:
    doc = Document(
        page_content="Hệ thống hỏi đáp dựa trên kỹ thuật RAG để giảm thiểu hallucination của AI model.",
        metadata={"source": "architecture.md", "chunk_index": 0},
    )

    cleaned = QuestionAnsweringService._sanitize_unverified_acronym_expansions(
        "Hệ thống hỏi đáp dựa trên kỹ thuật RAG (Relevance-Aware Graph) để giảm thiểu hallucination của AI model.",
        [doc],
    )

    assert "Relevance-Aware Graph" not in cleaned
    assert "RAG" in cleaned


def test_sanitize_unverified_acronym_expansions_keeps_grounded_expansion() -> None:
    doc = Document(
        page_content="RAG (Retrieval-Augmented Generation) là cách kết hợp truy xuất và sinh câu trả lời.",
        metadata={"source": "architecture.md", "chunk_index": 0},
    )
    answer = "Hệ thống hỏi đáp sử dụng RAG (Retrieval-Augmented Generation) để bám sát tài liệu."

    cleaned = QuestionAnsweringService._sanitize_unverified_acronym_expansions(answer, [doc])

    assert cleaned == answer


def test_ask_removes_ungrounded_acronym_expansion_from_llm_answer() -> None:
    question = "RAG là gì trong tài liệu?"
    doc = Document(
        page_content="Hệ thống hỏi đáp dựa trên kỹ thuật RAG để giảm thiểu hallucination của AI model.",
        metadata={"source": "architecture.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={question: [doc]})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=HallucinatedAcronymLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    result = service.ask(question)

    assert result.context_found is True
    assert "Relevance-Aware Graph" not in result.answer
    assert "RAG" in result.answer


def test_visual_prompt_contract_avoids_context_wording() -> None:
    assert "CONTEXT" not in build_visual_first_system_prompt()
    assert "CONTEXT" not in build_visual_first_human_prompt()
    assert "TÀI LIỆU:" in build_visual_first_human_prompt()
    assert "Không tự mở rộng hoặc giải thích từ viết tắt" in build_visual_first_system_prompt()


def test_build_overview_diagram_block_uses_flowchart_for_process_intent() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    branches = OrderedDict(
        {
            "Giai doan 1": ["Khoi dong", "Thu thap du lieu"],
            "Giai doan 2": ["Xu ly", "Danh gia"],
        }
    )
    diagram = service._build_overview_diagram_block(
        branches,
        normalized_question="lap lo trinh thoi gian du an",
        context_docs=[],
    )

    assert "```mermaid" in diagram
    assert "flowchart LR" in diagram


def test_build_overview_diagram_block_uses_mindmap_for_overview_intent() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    branches = OrderedDict(
        {
            "Nen tang": ["Frontend", "Backend"],
            "Nguoi dung": ["Hoc vien", "Giang vien"],
            "Van hanh": ["Bao tri", "Bao cao"],
            "Bao mat": ["Phan quyen", "Nhat ky"],
        }
    )
    diagram = service._build_overview_diagram_block(
        branches,
        normalized_question="tong quan he thong",
        context_docs=[],
    )

    assert "```mermaid" in diagram
    assert "mindmap" in diagram


def test_flowchart_diagram_wraps_long_labels_for_readability() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    diagram = service._build_flowchart_diagram_block(
        entries=[
            ("Lap ke hoach va kiem soat qua trinh test", ["Xay dung ke hoach chi tiet cho dot kiem thu"]),
            ("Phan tich dieu kien va thiet ke test cases", ["Xac dinh dau vao va tieu chi"]),
        ],
        root_label="Quy trinh kiem thu co ban",
    )

    assert "flowchart LR" in diagram
    assert "classDef terminal" in diagram
    assert "|bước 1|" in diagram
    assert "<br/>" in diagram


def test_sequential_entries_use_flowchart_lr() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    branches = OrderedDict(
        {
            "Buoc 1": ["Lap ke hoach"],
            "Buoc 2": ["Thiet ke test case"],
            "Buoc 3": ["Thuc thi test"],
            "Buoc 4": ["Danh gia va bao cao"],
        }
    )

    diagram = service._build_overview_diagram_block(
        branches,
        normalized_question="tom tat quy trinh kiem thu",
        context_docs=[],
    )

    assert "flowchart LR" in diagram


def test_normalize_question_rewrites_image_intent_prompt() -> None:
    rewritten = QuestionAnsweringService._normalize_question("ảnh trong tài liệu nói về cái gì")

    assert "phân tích phần hình ảnh" in rewritten.lower()
    assert "liệt kê theo từng ảnh/trang" in rewritten.lower()


def test_image_question_adds_image_analysis_alias_query() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    queries = service._build_retrieval_queries(
        "ảnh trong tài liệu nói về cái gì",
        "ảnh trong tài liệu nói về cái gì",
    )

    assert any("image analysis" in query.lower() for query in queries)


def test_transform_intent_strips_plain_visual_heading_placeholders() -> None:
    doc = Document(
        page_content="Noi dung tai lieu ve quy tac lam viec.",
        metadata={"source": "quiz-source.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    noisy_answer = (
        "Cau hoi 1: Tai sao can tuan thu noi quy?\n"
        "A) De co tien\n"
        "B) De co ky luat\n"
        "C) De cho vui\n"
        "D) De giai tri\n\n"
        "Bảng so sánh:\n"
        "Mermaid flowchart:\n"
    )

    cleaned = service._ensure_visual_answer(
        noisy_answer,
        context_docs=[doc],
        normalized_question="tao cau hoi trac nghiem",
    )

    assert "Cau hoi 1" in cleaned
    assert "Bảng so sánh:" not in cleaned
    assert "Mermaid flowchart:" not in cleaned


def test_collect_branches_from_context_skips_image_noise_lines() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    doc = Document(
        page_content=(
            "[Image insights]\n"
            "Image 1: local_ocr BcDEFG\n"
            "Muc tieu: Hieu quy tac chao hoi\n"
            "Quy tac: Chao dung gio\n"
        ),
        metadata={"source": "slide.pptx", "chunk_index": 0},
    )

    branches = service._collect_branches_from_context([doc])

    assert "Muc tieu" in branches
    assert "Hieu quy tac chao hoi" in branches["Muc tieu"]
    assert all("Image" not in branch for branch in branches)


def test_collect_branches_from_context_skips_pptx_structural_lines() -> None:
    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    doc = Document(
        page_content=(
            "Title: Slide 7\n"
            "Layout: Blank\n"
            "Reading Order: 3-4\n"
            "Slide Blocks:\n"
            "- [3] bullet/text_box @ x=-191954,y=199903,w=5982191,h=685800: Ch\n"
            "Upload đa định dạng: PDF, DOCX, PPTX, TXT MD CSV, ảnh\n"
        ),
        metadata={"source": "slide.pptx", "chunk_index": 0},
    )

    branches = service._collect_branches_from_context([doc])

    assert "Upload đa định dạng" in branches
    assert "PDF, DOCX, PPTX, TXT MD CSV, ảnh" in branches["Upload đa định dạng"]
    assert "Title" not in branches
    assert "Layout" not in branches
    assert "Reading Order" not in branches
    assert "Slide Blocks" not in branches


def test_normalize_question_rewrites_quiz_with_no_repeat_constraint() -> None:
    rewritten = QuestionAnsweringService._normalize_question("tao cau hoi trac nghiem")

    assert "5-10 câu hỏi trắc nghiệm" in rewritten
    assert "không lặp lại câu hỏi hoặc đáp án" in rewritten


def test_clear_question_without_visual_request_stays_text_only() -> None:
    doc = Document(
        page_content=(
            "Han thanh toan: 30 ngay sau khi nhan hoa don.\n"
            "Dieu kien phat: 5 phan tram gia tri hop dong."
        ),
        metadata={"source": "contract.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    answer = "Han thanh toan la 30 ngay sau khi nhan hoa don."
    enriched = service._ensure_visual_answer(
        answer,
        context_docs=[doc],
        normalized_question="Han thanh toan la bao nhieu",
    )

    assert enriched == answer
    assert "```mermaid" not in enriched
    assert "### Bảng" not in enriched


def test_explicit_table_request_adds_table_support_when_missing() -> None:
    doc = Document(
        page_content=(
            "Phuong an A: chi phi thap, trien khai nhanh, rui ro trung binh.\n"
            "Phuong an B: chi phi cao, trien khai cham, rui ro thap."
        ),
        metadata={"source": "options.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    enriched = service._ensure_visual_answer(
        "So sanh hai phuong an theo chi phi, tien do va rui ro.",
        context_docs=[doc],
        normalized_question="Hay tao bang so sanh hai phuong an",
    )

    assert "### Bảng" in enriched
    assert "|" in enriched


def test_explicit_mermaid_request_adds_flowchart_when_missing() -> None:
    doc = Document(
        page_content=(
            "Buoc 1: Tiep nhan yeu cau\n"
            "Buoc 2: Phan loai\n"
            "Buoc 3: Xu ly\n"
            "Buoc 4: Kiem tra"
        ),
        metadata={"source": "workflow.md", "chunk_index": 0},
    )

    fake_repo = FakeVectorStoreRepository(docs_by_query={})
    service = QuestionAnsweringService(
        vector_store_repository=fake_repo,
        llm_provider=FakeLLMProvider(),
        backup_llm_provider=None,
        top_k=3,
        min_context_token_overlap=0.0,
        min_relevant_chunks=1,
        cache_ttl_seconds=0,
    )

    enriched = service._ensure_visual_answer(
        "Quy trinh gom 4 buoc lien tiep tu tiep nhan den kiem tra.",
        context_docs=[doc],
        normalized_question="Ve so do mermaid cho quy trinh xu ly",
    )

    assert "```mermaid" in enriched
    assert "flowchart" in enriched
