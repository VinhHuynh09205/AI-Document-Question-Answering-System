from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_auth_service
from app.models.schemas import AuthResponse, LoginRequest, RegisterRequest
from app.services.auth_exceptions import (
    InvalidCredentialsError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
)
from app.services.interfaces.auth_service import IAuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(
    payload: RegisterRequest,
    auth_service: IAuthService = Depends(get_auth_service),
) -> AuthResponse:
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
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    auth_service: IAuthService = Depends(get_auth_service),
) -> AuthResponse:
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
    )
