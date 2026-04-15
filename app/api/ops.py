from fastapi import APIRouter, Depends

from app.core.dependencies import get_vector_store_admin_service
from app.models.schemas import VectorStoreBackupResponse, VectorStoreStatusResponse
from app.services.interfaces.vector_store_admin_service import IVectorStoreAdminService

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/vector/status", response_model=VectorStoreStatusResponse)
def vector_status(
    vector_store_admin_service: IVectorStoreAdminService = Depends(get_vector_store_admin_service),
) -> VectorStoreStatusResponse:
    payload = vector_store_admin_service.status()
    return VectorStoreStatusResponse(**payload)


@router.post("/vector/backup", response_model=VectorStoreBackupResponse)
def create_vector_backup(
    vector_store_admin_service: IVectorStoreAdminService = Depends(get_vector_store_admin_service),
) -> VectorStoreBackupResponse:
    payload = vector_store_admin_service.create_backup()
    return VectorStoreBackupResponse(**payload)


@router.post("/vector/restore-latest", response_model=VectorStoreBackupResponse)
def restore_vector_backup(
    vector_store_admin_service: IVectorStoreAdminService = Depends(get_vector_store_admin_service),
) -> VectorStoreBackupResponse:
    payload = vector_store_admin_service.restore_latest()
    return VectorStoreBackupResponse(**payload)


@router.post("/vector/clear", response_model=VectorStoreBackupResponse)
def clear_vector_store(
    vector_store_admin_service: IVectorStoreAdminService = Depends(get_vector_store_admin_service),
) -> VectorStoreBackupResponse:
    payload = vector_store_admin_service.clear()
    return VectorStoreBackupResponse(**payload)
