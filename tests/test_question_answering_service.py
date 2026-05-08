from collections import OrderedDict

from langchain_core.documents import Document

from app.services.question_answering_service import QuestionAnsweringService


class FakeVectorStoreRepository:
    def __init__(
        self,
        docs_by_query: dict[str, list[Document]],
        keyword_docs_by_query: dict[str, list[Document]] | None = None,
    ) -> None:
        self._docs_by_query = docs_by_query
        self._keyword_docs_by_query = keyword_docs_by_query or {}
        self.calls: list[tuple[str, int, dict[str, str | list[str]] | None]] = []
        self.keyword_calls: list[tuple[str, int, dict[str, str | list[str]] | None]] = []

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


class FakeLLMProvider:
    def generate_grounded_answer(self, question: str, context_docs: list[Document]) -> str:
        joined_context = "\n".join(doc.page_content for doc in context_docs)
        return f"Q: {question}\n{joined_context}".strip()

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
    assert "csv" in extensions


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

    assert add_summary is True
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

    assert add_summary is True
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


def test_normalize_question_rewrites_quiz_with_no_repeat_constraint() -> None:
    rewritten = QuestionAnsweringService._normalize_question("tao cau hoi trac nghiem")

    assert "5-10 câu hỏi trắc nghiệm" in rewritten
    assert "không lặp lại câu hỏi hoặc đáp án" in rewritten
