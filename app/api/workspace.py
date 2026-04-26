import asyncio
import json
import logging
import re
import time
import unicodedata
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.config import Settings
from app.core.dependencies import (
    get_app_settings,
    get_current_username,
    get_ingestion_service,
    get_question_answering_service,
    get_rate_limiter,
    get_runtime_metrics,
    get_upload_job_service,
    get_workspace_service,
)
from app.models.entities import StoredDocument
from app.models.schemas import (
    AskRequest,
    AskResponse,
    ChatListResponse,
    ChatResponse,
    CreateChatRequest,
    DocumentListResponse,
    DocumentRecordResponse,
    MessageListResponse,
    MessageRecordResponse,
    RenameChatRequest,
    RenameDocumentRequest,
    UploadJobStatusResponse,
    UploadResponse,
)
from app.services.interfaces.document_ingestion_service import IDocumentIngestionService
from app.services.interfaces.question_answering_service import IQuestionAnsweringService
from app.services.interfaces.rate_limiter import IRateLimiter
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.interfaces.upload_job_service import IUploadJobService
from app.services.interfaces.workspace_service import IWorkspaceService
from app.services.qa_constants import FALLBACK_ANSWER


router = APIRouter(prefix="/workspace", tags=["workspace"])
logger = logging.getLogger(__name__)
_UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
_UPLOAD_JOB_EXECUTION_LOCK = Lock()
_PENDING_SCOPE_LOCK = Lock()
_PENDING_SCOPE_TTL_SECONDS = 15 * 60
_PENDING_SCOPE_REQUESTS: dict[str, tuple[str, float]] = {}

_DOC_ALL_RE = re.compile(r"\b(tat\s*ca|toan\s*bo|all\s*(documents?|docs?|files?|tai\s*lieu))\b", re.IGNORECASE)
_DOC_CONTEXT_INDEX_RE = re.compile(
    r"\b(?:tai\s*lieu|document|doc|file)\s*(?:so|#|thu)?\s*(\d{1,3})\b",
    re.IGNORECASE,
)
_DOC_BARE_INDEX_RE = re.compile(r"\b(\d{1,3})\b")
_DOC_CROSS_ALL_RE = re.compile(
    r"\b(trong\s*cac\s*tai\s*lieu|tai\s*lieu\s*nao|document\s*nao|among\s*documents?)\b",
    re.IGNORECASE,
)
_SCOPE_SENSITIVE_RE = re.compile(
    r"\b(tom\s*tat|summary|tong\s*quan|phan\s*tich|so\s*sanh|trich\s*xuat|mindmap|so\s*do|"
    r"bieu\s*do|diagram|chart|giai\s*thich|dich|ket\s*luan|liet\s*ke|danh\s*gia)\b",
    re.IGNORECASE,
)
_CROSS_DOCUMENT_COMPARE_RE = re.compile(
    r"\b(so\s*sanh|compare|doi\s*chieu|đối\s*chiếu|khac\s*biet|khác\s*biệt|"
    r"tuong\s*dong|tương\s*đồng|giong\s*nhau|giống\s*nhau|bang\s*so\s*sanh|bảng\s*so\s*sánh|"
    r"tong\s*hop|tổng\s*hợp)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class _DocumentSelection:
    selected_indexes: list[int]
    select_all: bool
    ask_for_confirmation: bool


@dataclass(slots=True)
class _AskRoutingDecision:
    effective_question: str
    metadata_filter: dict[str, str | list[str]]
    clarification_answer: str | None = None
    # When multiple specific documents are selected we store them so that
    # ask endpoints can iterate per-document rather than doing one combined search.
    scoped_documents: list[StoredDocument] | None = None
    # 1-based indexes in current workspace order (after deletes, indexes are compacted).
    scoped_document_numbers: list[int] | None = None
    # True when question requires one combined answer across selected docs (e.g. comparisons).
    prefer_combined_answer: bool = False


def _normalize_scope_text(value: str) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _document_aliases(name: str) -> set[str]:
    aliases: set[str] = set()
    full_norm = _normalize_scope_text(name)
    stem_norm = _normalize_scope_text(Path(name).stem)

    for candidate in (full_norm, stem_norm):
        if len(candidate) >= 3:
            aliases.add(candidate)

    # Keep only the stem tail to match cases where users shorten long filenames.
    stem_tokens = stem_norm.split()
    if len(stem_tokens) >= 3:
        aliases.add(" ".join(stem_tokens[-3:]))

    return aliases


def _extract_document_selection(
    question: str,
    documents: list[StoredDocument],
    *,
    allow_bare_numbers: bool,
) -> _DocumentSelection:
    if not documents:
        return _DocumentSelection(selected_indexes=[], select_all=False, ask_for_confirmation=False)

    normalized_question = _normalize_scope_text(question)
    select_all = bool(_DOC_ALL_RE.search(normalized_question) or _DOC_CROSS_ALL_RE.search(normalized_question))

    selected_indexes: set[int] = set()
    for match in _DOC_CONTEXT_INDEX_RE.finditer(normalized_question):
        candidate = int(match.group(1))
        if 1 <= candidate <= len(documents):
            selected_indexes.add(candidate)

    if allow_bare_numbers and not select_all:
        for match in _DOC_BARE_INDEX_RE.finditer(normalized_question):
            candidate = int(match.group(1))
            if 1 <= candidate <= len(documents):
                selected_indexes.add(candidate)

    for index, doc in enumerate(documents, start=1):
        for alias in _document_aliases(doc.original_name):
            if alias and alias in normalized_question:
                selected_indexes.add(index)
                break

    ask_for_confirmation = (
        not select_all
        and not selected_indexes
        and len(documents) > 1
        and bool(_SCOPE_SENSITIVE_RE.search(normalized_question))
    )

    return _DocumentSelection(
        selected_indexes=sorted(selected_indexes),
        select_all=select_all,
        ask_for_confirmation=ask_for_confirmation,
    )


def _build_scope_clarification_message(documents: list[StoredDocument]) -> str:
    lines = [
        "Workspace này đang có nhiều tài liệu.",
        "Bạn muốn mình xử lý tài liệu nào?",
        "Bạn có thể gọi theo số thứ tự upload hoặc tên file:",
    ]

    for index, doc in enumerate(documents, start=1):
        lines.append(f"- Tài liệu {index}: {doc.original_name}")

    lines.append(
        'Trả lời ví dụ: "tài liệu 1", "1 và 3", "<tên file>", hoặc "tất cả".'
    )
    return "\n".join(lines)


def _pending_scope_key(username: str, chat_id: str) -> str:
    return f"{username}:{chat_id}"


def _set_pending_scope_question(username: str, chat_id: str, question: str) -> None:
    now = time.time()
    with _PENDING_SCOPE_LOCK:
        _PENDING_SCOPE_REQUESTS[_pending_scope_key(username, chat_id)] = (question, now)
        expired_keys = [
            key
            for key, (_, ts) in _PENDING_SCOPE_REQUESTS.items()
            if now - ts > _PENDING_SCOPE_TTL_SECONDS
        ]
        for key in expired_keys:
            _PENDING_SCOPE_REQUESTS.pop(key, None)


def _get_pending_scope_question(username: str, chat_id: str) -> str | None:
    now = time.time()
    key = _pending_scope_key(username, chat_id)
    with _PENDING_SCOPE_LOCK:
        payload = _PENDING_SCOPE_REQUESTS.get(key)
        if payload is None:
            return None
        question, ts = payload
        if now - ts > _PENDING_SCOPE_TTL_SECONDS:
            _PENDING_SCOPE_REQUESTS.pop(key, None)
            return None
        return question


def _clear_pending_scope_question(username: str, chat_id: str) -> None:
    with _PENDING_SCOPE_LOCK:
        _PENDING_SCOPE_REQUESTS.pop(_pending_scope_key(username, chat_id), None)


def _build_metadata_filter(
    username: str,
    chat_id: str,
    scoped_documents: list[StoredDocument],
) -> dict[str, str | list[str]]:
    metadata_filter: dict[str, str | list[str]] = {
        "owner": username,
        "chat_id": chat_id,
    }
    if not scoped_documents:
        return metadata_filter

    source_paths: list[str] = []
    for doc in scoped_documents:
        if doc.stored_path and doc.stored_path not in source_paths:
            source_paths.append(doc.stored_path)

    if len(source_paths) == 1:
        metadata_filter["source"] = source_paths[0]
    elif len(source_paths) > 1:
        metadata_filter["source"] = source_paths

    return metadata_filter


def _resolve_selected_documents_from_ids(
    documents: list[StoredDocument],
    selected_document_ids: list[str] | None,
) -> tuple[list[StoredDocument], list[int]]:
    if not documents or not selected_document_ids:
        return [], []

    selected_id_set = {
        str(document_id).strip()
        for document_id in selected_document_ids
        if str(document_id).strip()
    }
    if not selected_id_set:
        return [], []

    scoped_documents: list[StoredDocument] = []
    scoped_document_numbers: list[int] = []
    for index, doc in enumerate(documents, start=1):
        if doc.document_id in selected_id_set:
            scoped_documents.append(doc)
            scoped_document_numbers.append(index)

    return scoped_documents, scoped_document_numbers


def _is_cross_document_compare_question(question: str) -> bool:
    normalized_question = _normalize_scope_text(question)
    return bool(_CROSS_DOCUMENT_COMPARE_RE.search(normalized_question))


def _inject_document_mapping_into_question(
    question: str,
    scoped_documents: list[StoredDocument],
    scoped_document_numbers: list[int] | None,
) -> str:
    if not scoped_documents or len(scoped_documents) <= 1:
        return question

    lines = [question.strip(), "", "Ngữ cảnh tài liệu được chọn (chỉ dùng các tài liệu này):"]
    for index, doc in enumerate(scoped_documents, start=1):
        doc_number = (
            scoped_document_numbers[index - 1]
            if scoped_document_numbers and index - 1 < len(scoped_document_numbers)
            else index
        )
        lines.append(f"- Tài liệu {doc_number}: {doc.original_name}")

    lines.append(
        "Yêu cầu bắt buộc: giữ đúng số tài liệu như trên khi trả lời, không tự đổi số hoặc trộn tài liệu ngoài danh sách."
    )
    return "\n".join(lines).strip()


def _resolve_ask_routing(
    *,
    username: str,
    chat_id: str,
    question: str,
    selected_document_ids: list[str] | None,
    workspace_service: IWorkspaceService,
) -> _AskRoutingDecision:
    documents = workspace_service.list_documents(username=username, chat_id=chat_id)
    explicit_scoped_documents, explicit_scoped_document_numbers = _resolve_selected_documents_from_ids(
        documents,
        selected_document_ids,
    )

    if explicit_scoped_documents:
        _clear_pending_scope_question(username=username, chat_id=chat_id)
        return _AskRoutingDecision(
            effective_question=question,
            metadata_filter=_build_metadata_filter(username, chat_id, explicit_scoped_documents),
            scoped_documents=(
                explicit_scoped_documents
                if len(explicit_scoped_documents) > 1
                else None
            ),
            scoped_document_numbers=(
                explicit_scoped_document_numbers
                if len(explicit_scoped_documents) > 1
                else None
            ),
            prefer_combined_answer=(
                len(explicit_scoped_documents) > 1
                and _is_cross_document_compare_question(question)
            ),
        )

    pending_question = _get_pending_scope_question(username=username, chat_id=chat_id)

    if pending_question and documents:
        follow_up_selection = _extract_document_selection(
            question,
            documents,
            allow_bare_numbers=True,
        )
        if follow_up_selection.select_all or follow_up_selection.selected_indexes:
            scoped_documents = (
                documents
                if follow_up_selection.select_all
                else [documents[index - 1] for index in follow_up_selection.selected_indexes]
            )
            _clear_pending_scope_question(username=username, chat_id=chat_id)
            prefer_combined_answer = _is_cross_document_compare_question(pending_question)
            return _AskRoutingDecision(
                effective_question=pending_question,
                metadata_filter=_build_metadata_filter(username, chat_id, scoped_documents),
                scoped_documents=scoped_documents if len(scoped_documents) > 1 else None,
                scoped_document_numbers=(
                    follow_up_selection.selected_indexes
                    if len(scoped_documents) > 1 and follow_up_selection.selected_indexes
                    else None
                ),
                prefer_combined_answer=prefer_combined_answer,
            )
        _clear_pending_scope_question(username=username, chat_id=chat_id)

    if not documents:
        return _AskRoutingDecision(
            effective_question=question,
            metadata_filter=_build_metadata_filter(username, chat_id, []),
        )

    selection = _extract_document_selection(
        question,
        documents,
        allow_bare_numbers=False,
    )

    if selection.ask_for_confirmation:
        _set_pending_scope_question(username=username, chat_id=chat_id, question=question)
        return _AskRoutingDecision(
            effective_question=question,
            metadata_filter=_build_metadata_filter(username, chat_id, []),
            clarification_answer=_build_scope_clarification_message(documents),
        )

    scoped_documents = (
        documents
        if selection.select_all or not selection.selected_indexes
        else [documents[index - 1] for index in selection.selected_indexes]
    )

    return _AskRoutingDecision(
        effective_question=question,
        metadata_filter=_build_metadata_filter(username, chat_id, scoped_documents),
        scoped_documents=scoped_documents if len(scoped_documents) > 1 and selection.selected_indexes else None,
        scoped_document_numbers=(
            selection.selected_indexes
            if len(scoped_documents) > 1 and selection.selected_indexes
            else None
        ),
        prefer_combined_answer=(
            len(scoped_documents) > 1
            and bool(selection.selected_indexes)
            and _is_cross_document_compare_question(question)
        ),
    )


async def _save_upload_file(upload: UploadFile, output_path: Path) -> None:
    try:
        with output_path.open("wb") as handle:
            while True:
                chunk = await upload.read(_UPLOAD_CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                handle.write(chunk)
    finally:
        await upload.close()


def _cleanup_saved_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("workspace_upload_cleanup_failed path=%s", path)


def _extract_upload_error_detail(exc: Exception) -> str:
    if isinstance(exc, RuntimeError) and "sentence-transformers" in str(exc):
        return (
            "Local semantic embeddings are not available. "
            "Set LOCAL_SEMANTIC_EMBEDDINGS=false or rebuild with local embedding dependencies."
        )
    return "Failed to process uploaded files"


def _run_upload_job(
    *,
    job_id: str,
    username: str,
    chat_id: str,
    saved_paths: list[Path],
    original_names: list[str],
    ingestion_service: IDocumentIngestionService,
    workspace_service: IWorkspaceService,
    upload_job_service: IUploadJobService,
) -> None:
    upload_job_service.mark_processing(job_id, message="Đang xử lý tài liệu")

    def _on_progress(progress_payload: dict[str, int | str]) -> None:
        raw_progress = progress_payload.get("progress")
        raw_files_processed = progress_payload.get("files_processed")
        raw_chunks_total = progress_payload.get("chunks_total")
        raw_chunks_indexed = progress_payload.get("chunks_indexed")
        upload_job_service.update_progress(
            job_id,
            stage=str(progress_payload.get("stage", "processing")),
            progress=int(raw_progress) if isinstance(raw_progress, int) else None,
            files_processed=(
                int(raw_files_processed)
                if isinstance(raw_files_processed, int)
                else None
            ),
            chunks_total=int(raw_chunks_total) if isinstance(raw_chunks_total, int) else None,
            chunks_indexed=int(raw_chunks_indexed) if isinstance(raw_chunks_indexed, int) else None,
        )

    try:
        # FAISS in-memory state is shared, so writes are serialized to avoid race conditions.
        with _UPLOAD_JOB_EXECUTION_LOCK:
            result = ingestion_service.ingest(
                saved_paths,
                {"owner": username, "chat_id": chat_id},
                _on_progress,
            )
        workspace_service.record_documents(
            username=username,
            chat_id=chat_id,
            saved_paths=saved_paths,
            original_names=original_names,
        )
        upload_job_service.mark_completed(
            job_id,
            files_processed=result.files_processed,
            chunks_indexed=result.chunks_indexed,
            message="Files uploaded successfully",
        )
    except Exception as exc:
        logger.exception("workspace_upload_background_job_failed job_id=%s", job_id)
        _cleanup_saved_files(saved_paths)
        upload_job_service.mark_failed(
            job_id,
            error=_extract_upload_error_detail(exc),
            message="Upload processing failed",
        )


@router.post("/chats", response_model=ChatResponse)
def create_chat(
    payload: CreateChatRequest,
    username: str = Depends(get_current_username),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
) -> ChatResponse:
    chat = workspace_service.create_chat(username=username, title=payload.title)
    return ChatResponse(chat_id=chat.chat_id, title=chat.title, created_at=chat.created_at)


@router.get("/chats", response_model=ChatListResponse)
def list_chats(
    username: str = Depends(get_current_username),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
) -> ChatListResponse:
    chats = workspace_service.list_chats(username)
    return ChatListResponse(
        chats=[
            ChatResponse(chat_id=chat.chat_id, title=chat.title, created_at=chat.created_at)
            for chat in chats
        ]
    )


@router.get("/chats/{chat_id}/documents", response_model=DocumentListResponse)
def list_chat_documents(
    chat_id: str,
    username: str = Depends(get_current_username),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
) -> DocumentListResponse:
    try:
        workspace_service.ensure_chat(username=username, chat_id=chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found") from exc

    documents = workspace_service.list_documents(username=username, chat_id=chat_id)
    return DocumentListResponse(
        documents=[
            DocumentRecordResponse(
                document_id=doc.document_id,
                original_name=doc.original_name,
                stored_path=doc.stored_path,
                created_at=doc.created_at,
                upload_index=index,
            )
            for index, doc in enumerate(documents, start=1)
        ]
    )


@router.get("/chats/{chat_id}/messages", response_model=MessageListResponse)
def list_chat_messages(
    chat_id: str,
    username: str = Depends(get_current_username),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
) -> MessageListResponse:
    try:
        workspace_service.ensure_chat(username=username, chat_id=chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found") from exc

    messages = workspace_service.list_messages(username=username, chat_id=chat_id)
    return MessageListResponse(
        messages=[
            MessageRecordResponse(
                message_id=msg.message_id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at,
            )
            for msg in messages
        ]
    )


@router.post("/chats/{chat_id}/upload", response_model=UploadResponse)
async def upload_to_chat(
    chat_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    username: str = Depends(get_current_username),
    ingestion_service: IDocumentIngestionService = Depends(get_ingestion_service),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
    upload_job_service: IUploadJobService = Depends(get_upload_job_service),
    rate_limiter: IRateLimiter = Depends(get_rate_limiter),
    runtime_metrics: IRuntimeMetrics = Depends(get_runtime_metrics),
    settings: Settings = Depends(get_app_settings),
) -> UploadResponse:
    try:
        workspace_service.ensure_chat(username=username, chat_id=chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found") from exc

    client_key = f"{username}:upload"
    allowed, retry_after = rate_limiter.consume("upload", client_key)
    if not allowed:
        runtime_metrics.increment_rate_limited_requests()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    allowed_extensions = settings.get_supported_upload_extensions()
    primary_upload_root = Path(settings.upload_dir) / username / chat_id
    fallback_upload_root = Path(settings.upload_dir) / chat_id

    try:
        primary_upload_root.mkdir(parents=True, exist_ok=True)
        upload_root = primary_upload_root
    except PermissionError:
        logger.warning(
            "workspace_upload_primary_path_unwritable username=%s chat_id=%s path=%s",
            username,
            chat_id,
            primary_upload_root,
        )
        try:
            fallback_upload_root.mkdir(parents=True, exist_ok=True)
            upload_root = fallback_upload_root
        except OSError as exc:
            logger.exception("workspace_upload_storage_not_writable path=%s", fallback_upload_root)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Upload storage is not writable. Please contact the administrator.",
            ) from exc
    except OSError as exc:
        logger.exception("workspace_upload_storage_error path=%s", primary_upload_root)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload storage is unavailable. Please try again later.",
        ) from exc

    saved_paths: list[Path] = []
    original_names: list[str] = []

    for upload in files:
        original_name = upload.filename or "unknown"
        extension = Path(original_name).suffix.lower()
        if extension not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {extension}")

        safe_name = f"{uuid4().hex}_{Path(original_name).name}"
        output_path = upload_root / safe_name
        try:
            await _save_upload_file(upload, output_path)
        except OSError as exc:
            logger.exception("workspace_upload_file_write_failed path=%s", output_path)
            _cleanup_saved_files(saved_paths)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to write uploaded file: {original_name}",
            ) from exc
        saved_paths.append(output_path)
        original_names.append(original_name)

    job = upload_job_service.create_job(
        username=username,
        chat_id=chat_id,
        original_names=original_names,
    )

    worker = Thread(
        target=_run_upload_job,
        kwargs={
            "job_id": job["job_id"],
            "username": username,
            "chat_id": chat_id,
            "saved_paths": saved_paths,
            "original_names": original_names,
            "ingestion_service": ingestion_service,
            "workspace_service": workspace_service,
            "upload_job_service": upload_job_service,
        },
        daemon=True,
        name=f"upload-job-{job['job_id'][:8]}",
    )
    worker.start()

    return UploadResponse(
        message="Files accepted for background indexing",
        files_processed=0,
        chunks_indexed=0,
        original_names=original_names,
        job_id=job["job_id"],
        status=job["status"],
        status_url=f"/api/v1/workspace/chats/{chat_id}/upload-jobs/{job['job_id']}",
    )


def _ask_per_document(
    question: str,
    scoped_documents: list[StoredDocument],
    scoped_document_numbers: list[int] | None,
    base_filter: dict[str, str | list[str]],
    question_answering_service: IQuestionAnsweringService,
    top_k: int | None = None,
) -> tuple[str, list[str]]:
    """Run one ask per document and combine into a labelled answer."""
    parts: list[str] = []
    all_sources: list[str] = []

    for idx, doc in enumerate(scoped_documents, start=1):
        per_doc_filter = {**base_filter, "source": doc.stored_path}
        result = question_answering_service.ask(
            question,
            metadata_filter=per_doc_filter,
            top_k=top_k,
        )
        doc_number = (
            scoped_document_numbers[idx - 1]
            if scoped_document_numbers and idx - 1 < len(scoped_document_numbers)
            else idx
        )
        label = f"**Tài liệu {doc_number} ({doc.original_name}):**"
        if result.context_found:
            parts.append(f"{label}\n{result.answer}")
            all_sources.extend(result.sources)
        else:
            parts.append(f"{label}\nKhông tìm thấy nội dung liên quan trong tài liệu này.")

    return "\n\n".join(parts), _deduplicate_sources(all_sources)


def _deduplicate_sources(sources: list[str]) -> list[str]:
    unique_sources: list[str] = []
    seen: set[str] = set()

    for source in sources:
        normalized = str(source).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_sources.append(normalized)

    return unique_sources


@router.get("/chats/{chat_id}/upload-jobs/{job_id}", response_model=UploadJobStatusResponse)
def get_upload_job_status(
    chat_id: str,
    job_id: str,
    username: str = Depends(get_current_username),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
    upload_job_service: IUploadJobService = Depends(get_upload_job_service),
) -> UploadJobStatusResponse:
    try:
        workspace_service.ensure_chat(username=username, chat_id=chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found") from exc

    job = upload_job_service.get_job(job_id=job_id, username=username, chat_id=chat_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload job not found")

    return UploadJobStatusResponse(**job)


@router.post("/chats/{chat_id}/ask", response_model=AskResponse)
def ask_in_chat(
    chat_id: str,
    request: Request,
    payload: AskRequest,
    username: str = Depends(get_current_username),
    question_answering_service: IQuestionAnsweringService = Depends(get_question_answering_service),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
    rate_limiter: IRateLimiter = Depends(get_rate_limiter),
    runtime_metrics: IRuntimeMetrics = Depends(get_runtime_metrics),
) -> AskResponse:
    try:
        workspace_service.ensure_chat(username=username, chat_id=chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found") from exc

    client_key = f"{username}:ask"
    allowed, retry_after = rate_limiter.consume("ask", client_key)
    if not allowed:
        runtime_metrics.increment_rate_limited_requests()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    workspace_service.add_message(
        username=username,
        chat_id=chat_id,
        role="user",
        content=payload.question,
    )

    routing = _resolve_ask_routing(
        username=username,
        chat_id=chat_id,
        question=payload.question,
        selected_document_ids=payload.selected_document_ids,
        workspace_service=workspace_service,
    )

    if routing.clarification_answer:
        workspace_service.add_message(
            username=username,
            chat_id=chat_id,
            role="assistant",
            content=routing.clarification_answer,
        )
        return AskResponse(answer=routing.clarification_answer, sources=[])

    # When multiple specific documents are selected, query each separately so
    # that every document is represented equally in the final answer,
    # except for cross-document compare questions that require one combined view.
    if routing.scoped_documents and len(routing.scoped_documents) > 1 and not routing.prefer_combined_answer:
        base_filter = {
            k: v for k, v in routing.metadata_filter.items() if k != "source"
        }
        combined_answer, combined_sources = _ask_per_document(
            routing.effective_question,
            routing.scoped_documents,
            routing.scoped_document_numbers,
            base_filter,
            question_answering_service,
            top_k=payload.top_k,
        )
        workspace_service.add_message(
            username=username,
            chat_id=chat_id,
            role="assistant",
            content=combined_answer,
        )
        return AskResponse(answer=combined_answer, sources=combined_sources)

    effective_question = routing.effective_question
    if routing.prefer_combined_answer and routing.scoped_documents and len(routing.scoped_documents) > 1:
        effective_question = _inject_document_mapping_into_question(
            routing.effective_question,
            routing.scoped_documents,
            routing.scoped_document_numbers,
        )

    result = question_answering_service.ask(
        effective_question,
        metadata_filter=routing.metadata_filter,
        top_k=payload.top_k,
    )

    if not result.context_found:
        runtime_metrics.increment_fallback_answers()
        assistant_answer = FALLBACK_ANSWER
        workspace_service.add_message(
            username=username,
            chat_id=chat_id,
            role="assistant",
            content=assistant_answer,
        )
        return AskResponse(answer=assistant_answer, sources=[])

    workspace_service.add_message(
        username=username,
        chat_id=chat_id,
        role="assistant",
        content=result.answer,
    )

    return AskResponse(answer=result.answer, sources=result.sources)


@router.post("/chats/{chat_id}/ask/stream")
async def ask_in_chat_stream(
    chat_id: str,
    request: Request,
    payload: AskRequest,
    username: str = Depends(get_current_username),
    question_answering_service: IQuestionAnsweringService = Depends(get_question_answering_service),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
    rate_limiter: IRateLimiter = Depends(get_rate_limiter),
    runtime_metrics: IRuntimeMetrics = Depends(get_runtime_metrics),
) -> StreamingResponse:
    try:
        workspace_service.ensure_chat(username=username, chat_id=chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found") from exc

    client_key = f"{username}:ask"
    allowed, retry_after = rate_limiter.consume("ask", client_key)
    if not allowed:
        runtime_metrics.increment_rate_limited_requests()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    workspace_service.add_message(
        username=username,
        chat_id=chat_id,
        role="user",
        content=payload.question,
    )

    routing = _resolve_ask_routing(
        username=username,
        chat_id=chat_id,
        question=payload.question,
        selected_document_ids=payload.selected_document_ids,
        workspace_service=workspace_service,
    )

    if routing.clarification_answer:
        clarification = routing.clarification_answer

        async def _clarification_generator() -> AsyncIterator[str]:
            workspace_service.add_message(
                username=username,
                chat_id=chat_id,
                role="assistant",
                content=clarification,
            )
            yield f"data: {json.dumps({'token': clarification})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"

        return StreamingResponse(
            _clarification_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _event_generator() -> AsyncIterator[str]:
        full_answer_parts: list[str] = []
        collected_sources: list[str] = []
        try:
            # When multiple specific documents are selected, stream each document separately,
            # except for cross-document compare questions that should be answered once.
            if routing.scoped_documents and len(routing.scoped_documents) > 1 and not routing.prefer_combined_answer:
                base_filter = {
                    k: v for k, v in routing.metadata_filter.items() if k != "source"
                }
                for doc_idx, doc in enumerate(routing.scoped_documents, start=1):
                    doc_number = (
                        routing.scoped_document_numbers[doc_idx - 1]
                        if routing.scoped_document_numbers and doc_idx - 1 < len(routing.scoped_document_numbers)
                        else doc_idx
                    )
                    header = f"**Tài liệu {doc_number} ({doc.original_name}):**\n"
                    full_answer_parts.append(header)
                    yield f"data: {json.dumps({'token': header})}\n\n"

                    per_doc_filter = {**base_filter, "source": doc.stored_path}
                    per_doc_result = question_answering_service.ask(
                        routing.effective_question,
                        metadata_filter=per_doc_filter,
                        top_k=payload.top_k,
                    )
                    if per_doc_result.context_found:
                        doc_answer = per_doc_result.answer
                        collected_sources.extend(per_doc_result.sources)
                    else:
                        doc_answer = "Không tìm thấy nội dung liên quan trong tài liệu này."

                    full_answer_parts.append(doc_answer)
                    yield f"data: {json.dumps({'token': doc_answer})}\n\n"

                    if doc_idx < len(routing.scoped_documents):
                        sep = "\n\n"
                        full_answer_parts.append(sep)
                        yield f"data: {json.dumps({'token': sep})}\n\n"
            else:
                effective_question = routing.effective_question
                if routing.prefer_combined_answer and routing.scoped_documents and len(routing.scoped_documents) > 1:
                    effective_question = _inject_document_mapping_into_question(
                        routing.effective_question,
                        routing.scoped_documents,
                        routing.scoped_document_numbers,
                    )
                result = question_answering_service.ask(
                    effective_question,
                    metadata_filter=routing.metadata_filter,
                    top_k=payload.top_k,
                )
                if result.context_found:
                    streamed_answer = result.answer
                    collected_sources.extend(result.sources)
                else:
                    streamed_answer = FALLBACK_ANSWER
                    runtime_metrics.increment_fallback_answers()

                full_answer_parts.append(streamed_answer)
                yield f"data: {json.dumps({'token': streamed_answer})}\n\n"
        except Exception:
            logger.exception("ask_stream_failed")

        full_answer = "".join(full_answer_parts).strip()
        if not full_answer:
            full_answer = FALLBACK_ANSWER
            runtime_metrics.increment_fallback_answers()

        workspace_service.add_message(
            username=username,
            chat_id=chat_id,
            role="assistant",
            content=full_answer,
        )

        yield f"data: {json.dumps({'done': True, 'sources': _deduplicate_sources(collected_sources)})}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.put("/chats/{chat_id}", response_model=ChatResponse)
def rename_chat(
    chat_id: str,
    payload: RenameChatRequest,
    username: str = Depends(get_current_username),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
) -> ChatResponse:
    try:
        chat = workspace_service.rename_chat(username=username, chat_id=chat_id, new_title=payload.title)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ChatResponse(chat_id=chat.chat_id, title=chat.title, created_at=chat.created_at)


@router.delete("/chats/{chat_id}")
def delete_chat(
    chat_id: str,
    username: str = Depends(get_current_username),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
):
    deleted = workspace_service.delete_chat(username=username, chat_id=chat_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return {"ok": True}


@router.put("/chats/{chat_id}/documents/{document_id}", response_model=DocumentRecordResponse)
def rename_document(
    chat_id: str,
    document_id: str,
    payload: RenameDocumentRequest,
    username: str = Depends(get_current_username),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
) -> DocumentRecordResponse:
    try:
        workspace_service.ensure_chat(username=username, chat_id=chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found") from exc
    try:
        doc = workspace_service.rename_document(username=username, document_id=document_id, new_name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DocumentRecordResponse(
        document_id=doc.document_id, original_name=doc.original_name,
        stored_path=doc.stored_path, created_at=doc.created_at,
    )


@router.delete("/chats/{chat_id}/documents/{document_id}")
def delete_document(
    chat_id: str,
    document_id: str,
    username: str = Depends(get_current_username),
    workspace_service: IWorkspaceService = Depends(get_workspace_service),
):
    try:
        workspace_service.ensure_chat(username=username, chat_id=chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found") from exc
    deleted = workspace_service.delete_document(username=username, document_id=document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"ok": True}
