import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.container import build_container
from app.core.frontend_cache_control_middleware import FrontendCacheControlMiddleware
from app.core.logging_config import configure_logging
from app.core.request_context_middleware import RequestContextMiddleware
from app.core.security_headers_middleware import SecurityHeadersMiddleware


logger = logging.getLogger(__name__)


def _rebuild_vector_store_if_needed(application: FastAPI) -> None:
    container = application.state.container
    requires_rebuild = bool(
        getattr(container.vector_store_repository, "requires_startup_rebuild", lambda: False)()
    )
    if not requires_rebuild:
        return

    stored_documents = container.workspace_service.list_all_documents()
    if not stored_documents:
        logger.info("vector_store_startup_rebuild_skipped reason=no_stored_documents")
        return

    grouped_paths: dict[tuple[str, str], list[Path]] = defaultdict(list)
    seen_paths: set[tuple[str, str, str]] = set()
    missing_paths = 0

    for document in stored_documents:
        raw_path = str(document.stored_path or "").strip()
        if not raw_path:
            continue

        dedupe_key = (document.username, document.chat_id, raw_path)
        if dedupe_key in seen_paths:
            continue
        seen_paths.add(dedupe_key)

        file_path = Path(raw_path)
        if not file_path.exists():
            missing_paths += 1
            logger.warning(
                "vector_store_startup_rebuild_missing_file username=%s chat_id=%s path=%s",
                document.username,
                document.chat_id,
                raw_path,
            )
            continue

        grouped_paths[(document.username, document.chat_id)].append(file_path)

    if not grouped_paths:
        logger.warning(
            "vector_store_startup_rebuild_skipped reason=no_accessible_files documents=%s missing=%s",
            len(stored_documents),
            missing_paths,
        )
        return

    processed_groups = 0
    processed_files = 0
    indexed_chunks = 0

    for (username, chat_id), file_paths in grouped_paths.items():
        try:
            result = container.ingestion_service.ingest(
                file_paths,
                {"owner": username, "chat_id": chat_id},
            )
        except Exception:
            logger.exception(
                "vector_store_startup_rebuild_group_failed username=%s chat_id=%s files=%s",
                username,
                chat_id,
                len(file_paths),
            )
            continue

        processed_groups += 1
        processed_files += len(file_paths)
        indexed_chunks += result.chunks_indexed

    logger.info(
        "vector_store_startup_rebuild_completed groups=%s files=%s chunks=%s missing=%s",
        processed_groups,
        processed_files,
        indexed_chunks,
        missing_paths,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    container = build_container(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        runtime_container = application.state.container

        try:
            _rebuild_vector_store_if_needed(application)
        except Exception:
            logger.exception("vector_store_startup_rebuild_failed")

        try:
            runtime_container.upload_job_service.start_worker()
            logger.info("upload_worker_started")
        except Exception:
            logger.exception("upload_worker_start_failed")

        yield

        try:
            runtime_container.upload_job_service.stop_worker()
            logger.info("upload_worker_stopped")
        except Exception:
            logger.exception("upload_worker_stop_failed")

        try:
            runtime_container.vector_store_repository.save()
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

    app.add_middleware(FrontendCacheControlMiddleware)
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
