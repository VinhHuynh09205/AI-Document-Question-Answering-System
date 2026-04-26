import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.dependencies import (
    get_optional_current_username,
    get_question_answering_service,
    get_rate_limiter,
    get_runtime_metrics,
)
from app.models.schemas import AskRequest, AskResponse
from app.services.interfaces.question_answering_service import IQuestionAnsweringService
from app.services.interfaces.rate_limiter import IRateLimiter
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.qa_constants import FALLBACK_ANSWER

router = APIRouter(tags=["qa"])
logger = logging.getLogger(__name__)


@router.post("/ask", response_model=AskResponse)
def ask_question(
    request: Request,
    payload: AskRequest,
    username: str | None = Depends(get_optional_current_username),
    question_answering_service: IQuestionAnsweringService = Depends(get_question_answering_service),
    rate_limiter: IRateLimiter = Depends(get_rate_limiter),
    runtime_metrics: IRuntimeMetrics = Depends(get_runtime_metrics),
) -> AskResponse:
    client_key = request.client.host if request.client else "unknown"
    allowed, retry_after = rate_limiter.consume("ask", client_key)
    if not allowed:
        runtime_metrics.increment_rate_limited_requests()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        metadata_filter: dict[str, str | list[str]] | None = None
        if payload.chat_id is not None:
            if username is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required for chat-scoped queries",
                )
            metadata_filter = {"owner": username, "chat_id": payload.chat_id}

        result = question_answering_service.ask(payload.question, metadata_filter=metadata_filter, top_k=payload.top_k)
    except Exception:
        logger.exception("ask_endpoint_failed")
        runtime_metrics.increment_fallback_answers()
        return AskResponse(answer=FALLBACK_ANSWER, sources=[])

    # Enforce strict fallback message when context is not found.
    if not result.context_found:
        logger.info("ask_fallback_returned")
        runtime_metrics.increment_fallback_answers()
        return AskResponse(answer=FALLBACK_ANSWER, sources=[])

    logger.info("ask_success sources=%s", len(result.sources))
    return AskResponse(answer=result.answer, sources=result.sources)
