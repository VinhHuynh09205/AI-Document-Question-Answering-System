from collections import OrderedDict

from langchain_core.documents import Document

from app.services.question_answering_service import QuestionAnsweringService


class FakeVectorStoreRepository:
    def __init__(self, docs_by_query: dict[str, list[Document]]) -> None:
        self._docs_by_query = docs_by_query
        self.calls: list[tuple[str, int, dict[str, str | list[str]] | None]] = []

    def similarity_search(
        self,
        query: str,
        k: int,
        metadata_filter: dict[str, str | list[str]] | None = None,
    ) -> list[Document]:
        self.calls.append((query, k, metadata_filter))
        return list(self._docs_by_query.get(query, []))[:k]


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


def test_ensure_visual_answer_adds_table_and_diagram_for_plain_text() -> None:
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

    assert "### Bảng tổng hợp" in enriched
    assert "| Chủ đề | Điểm chính |" in enriched
    assert "### Sơ đồ tổng quan" in enriched
    assert "```mermaid" in enriched


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


def test_build_overview_diagram_block_uses_timeline_for_timeline_intent() -> None:
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
    assert "timeline" in diagram


def test_build_overview_diagram_block_uses_pie_for_distribution_intent() -> None:
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
            "Nhom A": ["Muc 1", "Muc 2", "Muc 3"],
            "Nhom B": ["Muc 4"],
        }
    )
    diagram = service._build_overview_diagram_block(
        branches,
        normalized_question="phan bo ty le noi dung",
        context_docs=[],
    )

    assert "```mermaid" in diagram
    assert "pie showData" in diagram
