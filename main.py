import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.container import build_container
from app.core.logging_config import configure_logging
from app.core.request_context_middleware import RequestContextMiddleware
from app.core.security_headers_middleware import SecurityHeadersMiddleware


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    container = build_container(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        try:
            container.vector_store_repository.save()
            logger.info("graceful_shutdown_vector_store_saved")
        except Exception:
            logger.exception("graceful_shutdown_vector_store_save_failed")

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Production-ready RAG service skeleton",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_allow_origins(),
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.get_cors_allow_methods(),
        allow_headers=settings.get_cors_allow_headers(),
    )
    if settings.enable_security_headers:
        app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.enable_hsts)

    app.add_middleware(RequestContextMiddleware)
    app.state.container = container
    web_dir = Path(__file__).resolve().parent / "web"
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index_page() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @app.get("/login", include_in_schema=False)
    def login_page() -> FileResponse:
        return FileResponse(web_dir / "login.html")

    @app.get("/admin", include_in_schema=False)
    def admin_page() -> FileResponse:
        return FileResponse(web_dir / "admin.html")

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
