from pathlib import Path

from fastapi import APIRouter, Depends

from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_runtime_metrics
from app.models.schemas import HealthResponse, MetricsResponse, ReadinessResponse
from app.services.interfaces.runtime_metrics import IRuntimeMetrics

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness_check(settings: Settings = Depends(get_app_settings)) -> ReadinessResponse:
    checks = {
        "upload_dir_exists": Path(settings.upload_dir).exists(),
        "vector_store_dir_exists": Path(settings.vector_store_path).exists(),
        "users_store_parent_exists": Path(settings.users_file_path).parent.exists(),
    }
    status = "ok" if all(checks.values()) else "degraded"
    return ReadinessResponse(status=status, checks=checks)


@router.get("/metrics", response_model=MetricsResponse)
def metrics_snapshot(
    runtime_metrics: IRuntimeMetrics = Depends(get_runtime_metrics),
) -> MetricsResponse:
    snapshot = runtime_metrics.snapshot()
    return MetricsResponse(**snapshot)
