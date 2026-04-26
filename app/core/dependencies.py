from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from app.core.config import Settings, get_settings
from app.core.container import AppContainer
from app.services.interfaces.auth_service import IAuthService
from app.services.interfaces.document_ingestion_service import IDocumentIngestionService
from app.services.interfaces.question_answering_service import IQuestionAnsweringService
from app.services.interfaces.rate_limiter import IRateLimiter
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.interfaces.admin_service import IAdminService
from app.services.interfaces.upload_job_service import IUploadJobService
from app.services.interfaces.vector_store_admin_service import IVectorStoreAdminService
from app.services.interfaces.workspace_service import IWorkspaceService


bearer_scheme = HTTPBearer(auto_error=False)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_ingestion_service(
    container: AppContainer = Depends(get_container),
) -> IDocumentIngestionService:
    return container.ingestion_service


def get_question_answering_service(
    container: AppContainer = Depends(get_container),
) -> IQuestionAnsweringService:
    return container.question_answering_service


def get_auth_service(
    container: AppContainer = Depends(get_container),
) -> IAuthService:
    return container.auth_service


def get_rate_limiter(
    container: AppContainer = Depends(get_container),
) -> IRateLimiter:
    return container.rate_limiter


def get_runtime_metrics(
    container: AppContainer = Depends(get_container),
) -> IRuntimeMetrics:
    return container.runtime_metrics


def get_vector_store_admin_service(
    container: AppContainer = Depends(get_container),
) -> IVectorStoreAdminService:
    return container.vector_store_admin_service


def get_app_settings(settings: Settings = Depends(get_settings)) -> Settings:
    return settings


def get_workspace_service(
    container: AppContainer = Depends(get_container),
) -> IWorkspaceService:
    return container.workspace_service


def get_upload_job_service(
    container: AppContainer = Depends(get_container),
) -> IUploadJobService:
    return container.upload_job_service


def get_admin_service(
    container: AppContainer = Depends(get_container),
) -> IAdminService:
    return container.admin_service


def get_optional_current_username(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> str | None:
    if credentials is None:
        return None

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc

    subject = str(payload.get("sub", "")).strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    return subject


def get_current_username(
    username: str | None = Depends(get_optional_current_username),
) -> str:
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return username


def get_current_admin_username(
    username: str = Depends(get_current_username),
    container: AppContainer = Depends(get_container),
) -> str:
    from app.repositories.interfaces.user_repository import IUserRepository

    auth_service = container.auth_service
    user_repo: IUserRepository = auth_service._user_repository  # noqa: SLF001
    user = user_repo.get_by_username(username)
    if user is None or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    return username
