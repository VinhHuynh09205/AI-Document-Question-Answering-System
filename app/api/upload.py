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
    get_vector_store_admin_service,
)
from app.models.schemas import UploadResponse
from app.services.interfaces.document_ingestion_service import IDocumentIngestionService
from app.services.interfaces.rate_limiter import IRateLimiter
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.interfaces.vector_store_admin_service import IVectorStoreAdminService

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    ingestion_service: IDocumentIngestionService = Depends(get_ingestion_service),
    vector_store_admin_service: IVectorStoreAdminService = Depends(get_vector_store_admin_service),
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
        clear_result = vector_store_admin_service.clear()
        logger.info(
            "upload_replace_mode_cleared_previous_index cleared=%s document_count=%s",
            clear_result.get("cleared"),
            clear_result.get("document_count"),
        )

    allowed_extensions = settings.get_supported_upload_extensions()
    saved_paths: list[Path] = []

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
        content = await upload.read()
        output_path.write_bytes(content)
        saved_paths.append(output_path)

    try:
        result = ingestion_service.ingest(saved_paths)
    except Exception as exc:
        logger.exception("upload_ingestion_failed")
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
