import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
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
    get_workspace_service,
)
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
    UploadResponse,
)
from app.services.interfaces.document_ingestion_service import IDocumentIngestionService
from app.services.interfaces.question_answering_service import IQuestionAnsweringService
from app.services.interfaces.rate_limiter import IRateLimiter
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.interfaces.workspace_service import IWorkspaceService
from app.services.qa_constants import FALLBACK_ANSWER


router = APIRouter(prefix="/workspace", tags=["workspace"])
logger = logging.getLogger(__name__)


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
            )
            for doc in documents
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
    upload_root = Path(settings.upload_dir) / username / chat_id
    upload_root.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    original_names: list[str] = []

    for upload in files:
        original_name = upload.filename or "unknown"
        extension = Path(original_name).suffix.lower()
        if extension not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {extension}")

        safe_name = f"{uuid4().hex}_{Path(original_name).name}"
        output_path = upload_root / safe_name
        content = await upload.read()
        output_path.write_bytes(content)
        saved_paths.append(output_path)
        original_names.append(original_name)

    try:
        result = await asyncio.to_thread(
            ingestion_service.ingest,
            saved_paths,
            {"owner": username, "chat_id": chat_id},
        )
    except Exception as exc:
        logger.exception("workspace_upload_failed")
        raise HTTPException(status_code=500, detail="Failed to process uploaded files") from exc

    workspace_service.record_documents(
        username=username,
        chat_id=chat_id,
        saved_paths=saved_paths,
        original_names=original_names,
    )

    return UploadResponse(
        message="Files uploaded successfully",
        files_processed=result.files_processed,
        chunks_indexed=result.chunks_indexed,
        original_names=original_names,
    )


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

    result = question_answering_service.ask(
        payload.question,
        metadata_filter={"owner": username, "chat_id": chat_id},
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

    async def _event_generator() -> AsyncIterator[str]:
        full_answer_parts: list[str] = []
        try:
            gen = question_answering_service.ask_stream(
                payload.question,
                metadata_filter={"owner": username, "chat_id": chat_id},
                top_k=payload.top_k,
            )
            for token in gen:
                full_answer_parts.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
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

        yield f"data: {json.dumps({'done': True})}\n\n"

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
