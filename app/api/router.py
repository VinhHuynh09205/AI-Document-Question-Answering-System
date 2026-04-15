from fastapi import APIRouter

from app.api.ask import router as ask_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.ops import router as ops_router
from app.api.upload import router as upload_router
from app.api.workspace import router as workspace_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(ops_router)
api_router.include_router(auth_router)
api_router.include_router(workspace_router)
api_router.include_router(upload_router)
api_router.include_router(ask_router)
