from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.dependencies import get_auth_service, get_rate_limiter, get_runtime_metrics
from app.models.schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    OAuthCompleteRequest,
    OAuthStartResponse,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.services.auth_exceptions import (
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    OAuthConfigurationError,
    OAuthProviderNotSupportedError,
    OAuthStateInvalidError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
)
from app.services.interfaces.auth_service import IAuthService
from app.services.interfaces.rate_limiter import IRateLimiter
from app.services.interfaces.runtime_metrics import IRuntimeMetrics

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=AuthResponse)
def register(
    request: Request,
    payload: RegisterRequest,
    auth_service: IAuthService = Depends(get_auth_service),
    rate_limiter: IRateLimiter = Depends(get_rate_limiter),
    runtime_metrics: IRuntimeMetrics = Depends(get_runtime_metrics),
) -> AuthResponse:
    allowed, retry_after = rate_limiter.consume("register", _client_key(request))
    if not allowed:
        runtime_metrics.increment_rate_limited_requests()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        result = auth_service.register(payload.username, payload.password)
    except RegistrationDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled",
        ) from exc
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        ) from exc

    return AuthResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
        username=payload.username.strip().lower(),
        role=result.role,
    )


@router.post("/login", response_model=AuthResponse)
def login(
    request: Request,
    payload: LoginRequest,
    auth_service: IAuthService = Depends(get_auth_service),
    rate_limiter: IRateLimiter = Depends(get_rate_limiter),
    runtime_metrics: IRuntimeMetrics = Depends(get_runtime_metrics),
) -> AuthResponse:
    allowed, retry_after = rate_limiter.consume("login", _client_key(request))
    if not allowed:
        runtime_metrics.increment_rate_limited_requests()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        result = auth_service.login(payload.username, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        ) from exc

    return AuthResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
        username=payload.username.strip().lower(),
        role=result.role,
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    auth_service: IAuthService = Depends(get_auth_service),
) -> ForgotPasswordResponse:
    result = auth_service.forgot_password(
        username=payload.username,
        redirect_uri=payload.redirect_uri or "",
    )
    return ForgotPasswordResponse(
        message=result.message,
        reset_token=result.reset_token,
        reset_url=result.reset_url,
    )


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    auth_service: IAuthService = Depends(get_auth_service),
) -> dict[str, str]:
    try:
        auth_service.reset_password(payload.token, payload.new_password)
    except InvalidPasswordResetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn",
        ) from exc

    return {"message": "Đặt lại mật khẩu thành công"}


@router.get("/oauth/{provider}/start", response_model=OAuthStartResponse)
def oauth_start(
    provider: str,
    redirect_uri: str | None = Query(default=None),
    auth_service: IAuthService = Depends(get_auth_service),
) -> OAuthStartResponse:
    try:
        result = auth_service.build_oauth_start_url(provider=provider, redirect_uri=redirect_uri or "")
    except OAuthProviderNotSupportedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OAuth provider không được hỗ trợ") from exc
    except OAuthConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except OAuthStateInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return OAuthStartResponse(authorization_url=result.authorization_url, state=result.state)


@router.post("/oauth/{provider}/complete", response_model=AuthResponse)
def oauth_complete(
    provider: str,
    payload: OAuthCompleteRequest,
    auth_service: IAuthService = Depends(get_auth_service),
) -> AuthResponse:
    try:
        username, token = auth_service.complete_oauth_login(
            provider=provider,
            code=payload.code,
            state=payload.state,
            redirect_uri=payload.redirect_uri or "",
        )
    except OAuthProviderNotSupportedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OAuth provider không được hỗ trợ") from exc
    except OAuthConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except OAuthStateInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RegistrationDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is disabled") from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return AuthResponse(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
        username=username,
        role=token.role,
    )
