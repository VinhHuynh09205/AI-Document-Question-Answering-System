import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.core.config import Settings
from app.core.dependencies import (
    get_app_settings,
    get_ingestion_service,
    get_rate_limiter,
    get_runtime_metrics,
    get_vector_store_repository,
)
from app.models.schemas import UploadResponse
from app.services.interfaces.document_ingestion_service import IDocumentIngestionService
from app.services.interfaces.rate_limiter import IRateLimiter
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)
_UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024


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
            logger.warning("upload_cleanup_failed path=%s", path)


def _clear_legacy_documents_only(vector_store_repository: IVectorStoreRepository) -> int:
    """Clear only legacy /upload chunks that have no workspace owner/chat metadata."""
    return vector_store_repository.delete_documents_by_metadata(
        {
            "owner": "None",
            "chat_id": "None",
        }
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    ingestion_service: IDocumentIngestionService = Depends(get_ingestion_service),
    vector_store_repository: IVectorStoreRepository = Depends(get_vector_store_repository),
    rate_limiter: IRateLimiter = Depends(get_rate_limiter),
    runtime_metrics: IRuntimeMetrics = Depends(get_runtime_metrics),
    settings: Settings = Depends(get_app_settings),
) -> UploadResponse:
    client_key = request.client.host if request.client else "unknown"
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

    if settings.replace_existing_documents_on_upload:
        removed_chunks = _clear_legacy_documents_only(vector_store_repository)
        if removed_chunks > 0:
            vector_store_repository.save()
        logger.info(
            "upload_replace_mode_cleared_legacy_docs removed_chunks=%s",
            removed_chunks,
        )

    allowed_extensions = settings.get_supported_upload_extensions()
    saved_paths: list[Path] = []

    try:
        Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.exception("upload_storage_error path=%s", settings.upload_dir)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload storage is unavailable. Please try again later.",
        ) from exc

    for upload in files:
        original_name = upload.filename or "unknown"
        extension = Path(original_name).suffix.lower()
        if extension not in allowed_extensions:
            logger.warning("upload_rejected_unsupported_extension extension=%s", extension)
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {extension}",
            )

        safe_name = f"{uuid4().hex}_{Path(original_name).name}"
        output_path = Path(settings.upload_dir) / safe_name
        try:
            await _save_upload_file(upload, output_path)
        except OSError as exc:
            logger.exception("upload_file_write_failed path=%s", output_path)
            _cleanup_saved_files(saved_paths)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to write uploaded file: {original_name}",
            ) from exc
        saved_paths.append(output_path)

    try:
        result = await asyncio.to_thread(ingestion_service.ingest, saved_paths)
    except RuntimeError as exc:
        logger.exception("upload_ingestion_failed")
        _cleanup_saved_files(saved_paths)
        if "sentence-transformers" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Local semantic embeddings are not available. "
                    "Set LOCAL_SEMANTIC_EMBEDDINGS=false or rebuild with local embedding dependencies."
                ),
            ) from exc
        raise HTTPException(status_code=500, detail="Failed to process uploaded files") from exc
    except Exception as exc:
        logger.exception("upload_ingestion_failed")
        _cleanup_saved_files(saved_paths)
        raise HTTPException(status_code=500, detail="Failed to process uploaded files") from exc

    logger.info(
        "upload_completed files=%s chunks_indexed=%s",
        result.files_processed,
        result.chunks_indexed,
    )

    return UploadResponse(
        message="Files uploaded successfully",
        files_processed=result.files_processed,
        chunks_indexed=result.chunks_indexed,
    )
