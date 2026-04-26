import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.core.config import Settings
from app.core.dependencies import get_admin_service, get_app_settings, get_current_admin_username
from app.models.admin_schemas import (
    AdminResetPasswordRequest,
    AdminUserListResponse,
    AdminUserResponse,
    AuditLogListResponse,
    DashboardStatsResponse,
    SetupFirstAdminRequest,
    SystemConfigResponse,
    SystemMetricsResponse,
    UpdateRoleRequest,
    UpdateStatusRequest,
    UsageAnalyticsResponse,
)
from app.services.interfaces.admin_service import IAdminService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/setup", response_model=AdminUserResponse)
def setup_first_admin(
    payload: SetupFirstAdminRequest,
    setup_secret: str | None = Header(default=None, alias="X-Admin-Setup-Secret"),
    settings: Settings = Depends(get_app_settings),
    admin_service: IAdminService = Depends(get_admin_service),
) -> AdminUserResponse:
    configured_secret = settings.admin_setup_secret.strip()
    if not configured_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin setup is disabled")
    if setup_secret is None or not secrets.compare_digest(setup_secret, configured_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid setup secret")

    try:
        user = admin_service.setup_first_admin(
            username=payload.username,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AdminUserResponse(
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/dashboard", response_model=DashboardStatsResponse)
def dashboard_stats(
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
) -> DashboardStatsResponse:
    data = admin_service.get_dashboard_stats()
    return DashboardStatsResponse(**data)


@router.get("/users", response_model=AdminUserListResponse)
def list_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
) -> AdminUserListResponse:
    data = admin_service.list_users(offset=offset, limit=limit)
    return AdminUserListResponse(
        users=[AdminUserResponse(**u) for u in data["users"]],
        total=data["total"],
        offset=data["offset"],
        limit=data["limit"],
    )


@router.get("/users/{username}", response_model=AdminUserResponse)
def get_user(
    username: str,
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
) -> AdminUserResponse:
    try:
        user = admin_service.get_user_detail(username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AdminUserResponse(
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.put("/users/{username}/role", response_model=AdminUserResponse)
def update_user_role(
    username: str,
    payload: UpdateRoleRequest,
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
) -> AdminUserResponse:
    try:
        user = admin_service.update_user_role(
            admin_username=admin_username,
            target_username=username,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminUserResponse(
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.put("/users/{username}/status", response_model=AdminUserResponse)
def update_user_status(
    username: str,
    payload: UpdateStatusRequest,
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
) -> AdminUserResponse:
    try:
        user = admin_service.update_user_status(
            admin_username=admin_username,
            target_username=username,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminUserResponse(
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.delete("/users/{username}")
def delete_user(
    username: str,
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
):
    try:
        deleted = admin_service.delete_user(
            admin_username=admin_username,
            target_username=username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"ok": True}


@router.post("/users/{username}/reset-password")
def admin_reset_password(
    username: str,
    payload: AdminResetPasswordRequest,
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
):
    try:
        admin_service.admin_reset_password(
            admin_username=admin_username,
            target_username=username,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/system/metrics", response_model=SystemMetricsResponse)
def system_metrics(
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
) -> SystemMetricsResponse:
    data = admin_service.get_system_metrics()
    return SystemMetricsResponse(**data)


@router.get("/system/config", response_model=SystemConfigResponse)
def system_config(
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
) -> SystemConfigResponse:
    data = admin_service.get_system_config()
    return SystemConfigResponse(**data)


@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
) -> AuditLogListResponse:
    data = admin_service.list_audit_logs(offset=offset, limit=limit)
    return AuditLogListResponse(**data)


@router.get("/analytics/usage", response_model=UsageAnalyticsResponse)
def usage_analytics(
    days: int = Query(default=30, ge=1, le=365),
    admin_username: str = Depends(get_current_admin_username),
    admin_service: IAdminService = Depends(get_admin_service),
) -> UsageAnalyticsResponse:
    data = admin_service.get_usage_analytics(days=days)
    return UsageAnalyticsResponse(**data)
