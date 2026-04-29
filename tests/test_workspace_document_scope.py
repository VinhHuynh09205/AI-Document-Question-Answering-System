import base64
import json

from app.api.workspace import (
    _ask_per_document,
    _attach_sources_metadata_to_message,
    _clear_pending_scope_question,
    _extract_document_selection,
    _get_pending_scope_question,
    _inject_document_mapping_into_question,
    _resolve_ask_routing,
    _set_pending_scope_question,
)
from app.models.entities import AnswerResult, StoredDocument


class _FakeWorkspaceService:
    def __init__(self, documents: list[StoredDocument]) -> None:
        self._documents = documents

    def list_documents(self, username: str, chat_id: str) -> list[StoredDocument]:
        return list(self._documents)


class _FakeQuestionAnsweringService:
    def ask(
        self,
        question: str,
        metadata_filter: dict[str, str | list[str]] | None = None,
        top_k: int | None = None,
    ) -> AnswerResult:
        source = str((metadata_filter or {}).get("source", ""))
        return AnswerResult(
            answer=f"Answer from {source}",
            sources=[source],
            context_found=True,
        )


def _make_documents() -> list[StoredDocument]:
    return [
        StoredDocument(
            document_id="doc-1",
            chat_id="chat-1",
            username="alice",
            original_name="hop-dong-2025.pdf",
            stored_path="/tmp/doc-1.pdf",
            created_at="2026-01-01T00:00:00Z",
        ),
        StoredDocument(
            document_id="doc-2",
            chat_id="chat-1",
            username="alice",
            original_name="bao-cao-doanh-thu.xlsx",
            stored_path="/tmp/doc-2.xlsx",
            created_at="2026-01-01T00:00:01Z",
        ),
        StoredDocument(
            document_id="doc-3",
            chat_id="chat-1",
            username="alice",
            original_name="ghi-chu-du-an.md",
            stored_path="/tmp/doc-3.md",
            created_at="2026-01-01T00:00:02Z",
        ),
    ]


def test_extract_document_selection_by_index_and_name() -> None:
    docs = _make_documents()
    selection = _extract_document_selection(
        "Tom tat tai lieu 2 va ghi chu du an",
        docs,
        allow_bare_numbers=False,
    )

    assert selection.ask_for_confirmation is False
    assert selection.select_all is False
    assert selection.selected_indexes == [2, 3]


def test_resolve_ask_routing_requests_confirmation_for_ambiguous_scope() -> None:
    docs = _make_documents()
    workspace_service = _FakeWorkspaceService(docs)

    _clear_pending_scope_question("alice", "chat-1")
    routing = _resolve_ask_routing(
        username="alice",
        chat_id="chat-1",
        question="Tom tat giup minh",
        selected_document_ids=None,
        workspace_service=workspace_service,
    )

    assert routing.clarification_answer is not None
    assert "Tài liệu 1" in routing.clarification_answer
    assert _get_pending_scope_question("alice", "chat-1") == "Tom tat giup minh"

    _clear_pending_scope_question("alice", "chat-1")


def test_resolve_ask_routing_uses_pending_question_with_follow_up_selection() -> None:
    docs = _make_documents()
    workspace_service = _FakeWorkspaceService(docs)

    _set_pending_scope_question("alice", "chat-1", "Tom tat noi dung chinh")
    routing = _resolve_ask_routing(
        username="alice",
        chat_id="chat-1",
        question="1 va 3",
        selected_document_ids=None,
        workspace_service=workspace_service,
    )

    assert routing.clarification_answer is None
    assert routing.effective_question == "Tom tat noi dung chinh"
    assert routing.metadata_filter.get("source") == ["/tmp/doc-1.pdf", "/tmp/doc-3.md"]
    assert routing.scoped_document_numbers == [1, 3]
    assert _get_pending_scope_question("alice", "chat-1") is None


def test_resolve_ask_routing_keeps_workspace_numbers_for_named_documents() -> None:
    docs = _make_documents()
    workspace_service = _FakeWorkspaceService(docs)

    routing = _resolve_ask_routing(
        username="alice",
        chat_id="chat-1",
        question="So sanh bao cao doanh thu va ghi chu du an",
        selected_document_ids=None,
        workspace_service=workspace_service,
    )

    assert routing.scoped_documents is not None
    assert [doc.original_name for doc in routing.scoped_documents] == [
        "bao-cao-doanh-thu.xlsx",
        "ghi-chu-du-an.md",
    ]
    assert routing.scoped_document_numbers == [2, 3]
    assert routing.prefer_combined_answer is True


def test_resolve_ask_routing_keeps_per_document_mode_for_non_compare_multi_doc_question() -> None:
    docs = _make_documents()
    workspace_service = _FakeWorkspaceService(docs)

    routing = _resolve_ask_routing(
        username="alice",
        chat_id="chat-1",
        question="Tom tat tai lieu 1 va tai lieu 3",
        selected_document_ids=None,
        workspace_service=workspace_service,
    )

    assert routing.scoped_documents is not None
    assert routing.scoped_document_numbers == [1, 3]
    assert routing.prefer_combined_answer is False


def test_inject_document_mapping_into_question_keeps_workspace_numbers() -> None:
    docs = _make_documents()

    mapped_question = _inject_document_mapping_into_question(
        "So sanh tai lieu 1 va tai lieu 3",
        [docs[0], docs[2]],
        [1, 3],
    )

    assert "So sanh tai lieu 1 va tai lieu 3" in mapped_question
    assert "- Tài liệu 1: hop-dong-2025.pdf" in mapped_question
    assert "- Tài liệu 3: ghi-chu-du-an.md" in mapped_question


def test_resolve_ask_routing_prefers_explicit_selected_document_ids() -> None:
    docs = _make_documents()
    workspace_service = _FakeWorkspaceService(docs)

    routing = _resolve_ask_routing(
        username="alice",
        chat_id="chat-1",
        question="Tom tat giup minh",
        selected_document_ids=["doc-1", "doc-3"],
        workspace_service=workspace_service,
    )

    assert routing.clarification_answer is None
    assert routing.metadata_filter.get("source") == ["/tmp/doc-1.pdf", "/tmp/doc-3.md"]
    assert routing.scoped_document_numbers == [1, 3]
    assert routing.prefer_combined_answer is False


def test_resolve_ask_routing_explicit_selected_document_ids_keep_compare_mode() -> None:
    docs = _make_documents()
    workspace_service = _FakeWorkspaceService(docs)

    routing = _resolve_ask_routing(
        username="alice",
        chat_id="chat-1",
        question="So sanh diem khac biet",
        selected_document_ids=["doc-1", "doc-3"],
        workspace_service=workspace_service,
    )

    assert routing.clarification_answer is None
    assert routing.scoped_document_numbers == [1, 3]
    assert routing.prefer_combined_answer is True


def test_ask_per_document_uses_workspace_numbers_in_labels() -> None:
    docs = _make_documents()
    qa_service = _FakeQuestionAnsweringService()

    answer, sources = _ask_per_document(
        question="Tom tat",
        scoped_documents=[docs[0], docs[2]],
        scoped_document_numbers=[1, 3],
        base_filter={"owner": "alice", "chat_id": "chat-1"},
        question_answering_service=qa_service,
    )

    assert "**Tài liệu 1 (hop-dong-2025.pdf):**" in answer
    assert "**Tài liệu 3 (ghi-chu-du-an.md):**" in answer
    assert "**Tài liệu 2 (ghi-chu-du-an.md):**" not in answer
    assert sources == ["/tmp/doc-1.pdf", "/tmp/doc-3.md"]


def test_resolve_ask_routing_uses_compacted_numbers_after_deletion() -> None:
    # Simulate current workspace state after deleting the old document #2.
    docs_after_deletion = [
        StoredDocument(
            document_id="doc-1",
            chat_id="chat-1",
            username="alice",
            original_name="hop-dong-2025.pdf",
            stored_path="/tmp/doc-1.pdf",
            created_at="2026-01-01T00:00:00Z",
        ),
        StoredDocument(
            document_id="doc-3",
            chat_id="chat-1",
            username="alice",
            original_name="ghi-chu-du-an.md",
            stored_path="/tmp/doc-3.md",
            created_at="2026-01-01T00:00:02Z",
        ),
    ]
    workspace_service = _FakeWorkspaceService(docs_after_deletion)

    routing = _resolve_ask_routing(
        username="alice",
        chat_id="chat-1",
        question="Tom tat tai lieu 2",
        selected_document_ids=None,
        workspace_service=workspace_service,
    )

    assert routing.clarification_answer is None
    assert routing.scoped_documents is None
    assert routing.metadata_filter.get("source") == "/tmp/doc-3.md"


def test_attach_sources_metadata_to_message_appends_hidden_marker() -> None:
    persisted = _attach_sources_metadata_to_message(
        "Noi dung tra loi",
        ["/tmp/doc-1.pdf", "/tmp/doc-1.pdf", " /tmp/doc-2.xlsx "],
    )

    assert persisted.startswith("Noi dung tra loi")
    assert "<!--aichatbox:sources:" in persisted

    encoded = persisted.split("<!--aichatbox:sources:", 1)[1].split("-->", 1)[0]
    decoded = base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    assert json.loads(decoded) == ["/tmp/doc-1.pdf", "/tmp/doc-2.xlsx"]


def test_attach_sources_metadata_to_message_keeps_plain_answer_without_sources() -> None:
    assert _attach_sources_metadata_to_message("Tra loi", []) == "Tra loi"
    assert _attach_sources_metadata_to_message("Tra loi", None) == "Tra loi"
