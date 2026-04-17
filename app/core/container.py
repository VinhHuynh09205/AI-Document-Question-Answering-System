from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.core.embedding_factory import build_embeddings
from app.core.llm_provider_factory import build_llm_provider
from app.repositories.faiss_vector_store_repository import FaissVectorStoreRepository
from app.repositories.sqlite_user_repository import SqliteUserRepository
from app.repositories.sqlite_workspace_repository import SqliteWorkspaceRepository
from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_loader_registry import DocumentLoaderRegistry
from app.services.document_loaders.csv_document_loader import CsvDocumentLoader
from app.services.document_loaders.doc_document_loader import DocDocumentLoader
from app.services.document_loaders.docx_document_loader import DocxDocumentLoader
from app.services.document_loaders.excel_document_loader import ExcelDocumentLoader
from app.services.document_loaders.html_document_loader import HtmlDocumentLoader
from app.services.document_loaders.json_document_loader import JsonDocumentLoader
from app.services.document_loaders.markdown_document_loader import MarkdownDocumentLoader
from app.services.document_loaders.pdf_document_loader import PdfDocumentLoader
from app.services.document_loaders.pptx_document_loader import PptxDocumentLoader
from app.services.document_loaders.text_document_loader import TextDocumentLoader
from app.services.document_loaders.xml_document_loader import XmlDocumentLoader
from app.services.in_memory_rate_limiter import InMemoryRateLimiter
from app.services.interfaces.document_ingestion_service import IDocumentIngestionService
from app.services.interfaces.auth_service import IAuthService
from app.services.interfaces.question_answering_service import IQuestionAnsweringService
from app.services.interfaces.rate_limiter import IRateLimiter
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.interfaces.vector_store_admin_service import IVectorStoreAdminService
from app.services.interfaces.workspace_service import IWorkspaceService
from app.services.auth_service import AuthService
from app.services.llm_providers.local_grounded_llm_provider import LocalGroundedLLMProvider
from app.services.question_answering_service import QuestionAnsweringService
from app.services.runtime_metrics import RuntimeMetrics
from app.services.text_chunking_service import TextChunkingService
from app.services.vector_store_admin_service import VectorStoreAdminService
from app.services.workspace_service import WorkspaceService
from app.utils.filesystem import ensure_directory


@dataclass(slots=True)
class AppContainer:
    ingestion_service: IDocumentIngestionService
    question_answering_service: IQuestionAnsweringService
    auth_service: IAuthService
    rate_limiter: IRateLimiter
    runtime_metrics: IRuntimeMetrics
    vector_store_repository: IVectorStoreRepository
    vector_store_admin_service: IVectorStoreAdminService
    workspace_service: IWorkspaceService


def build_container(settings: Settings) -> AppContainer:
    ensure_directory(Path(settings.upload_dir))
    ensure_directory(Path(settings.vector_store_path))
    ensure_directory(Path(settings.vector_backup_dir))
    if settings.get_database_backend() == "sqlite":
        ensure_directory(Path(settings.database_path).parent)
    ensure_directory(Path(settings.users_file_path).parent)

    embeddings = build_embeddings(settings)
    vector_store_repository = FaissVectorStoreRepository(
        index_dir=Path(settings.vector_store_path),
        embeddings=embeddings,
    )
    loader_registry = DocumentLoaderRegistry(
        loaders=[
            PdfDocumentLoader(),
            DocDocumentLoader(),
            DocxDocumentLoader(),
            ExcelDocumentLoader(),
            PptxDocumentLoader(),
            HtmlDocumentLoader(),
            JsonDocumentLoader(),
            XmlDocumentLoader(),
            TextDocumentLoader(),
            MarkdownDocumentLoader(),
            CsvDocumentLoader(),
        ]
    )
    chunking_service = TextChunkingService(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    ingestion_service = DocumentIngestionService(
        loader_registry=loader_registry,
        chunking_service=chunking_service,
        vector_store_repository=vector_store_repository,
    )
    llm_provider = build_llm_provider(settings)
    backup_llm_provider = LocalGroundedLLMProvider(max_answer_chars=settings.max_answer_chars)
    question_answering_service = QuestionAnsweringService(
        vector_store_repository=vector_store_repository,
        llm_provider=llm_provider,
        backup_llm_provider=backup_llm_provider,
        top_k=settings.top_k,
        min_context_token_overlap=settings.min_context_token_overlap,
        min_relevant_chunks=settings.min_relevant_chunks,
        cache_ttl_seconds=settings.qa_cache_ttl_seconds,
        cache_max_size=settings.qa_cache_max_size,
    )
    rate_limiter = InMemoryRateLimiter(
        limits=settings.get_rate_limit_config(),
        window_seconds=settings.rate_limit_window_seconds,
    )
    runtime_metrics = RuntimeMetrics()
    vector_store_admin_service = VectorStoreAdminService(
        vector_store_repository=vector_store_repository,
        backup_root_dir=Path(settings.vector_backup_dir),
    )

    if settings.get_database_backend() == "mysql":
        from app.repositories.mysql_user_repository import MySqlUserRepository
        from app.repositories.mysql_utils import MySqlConfig
        from app.repositories.mysql_workspace_repository import MySqlWorkspaceRepository

        mysql_config = MySqlConfig(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset=settings.mysql_charset,
        )
        workspace_repository = MySqlWorkspaceRepository(config=mysql_config)
        user_repository = MySqlUserRepository(config=mysql_config)
    else:
        workspace_repository = SqliteWorkspaceRepository(database_path=Path(settings.database_path))
        user_repository = SqliteUserRepository(database_path=Path(settings.database_path))

    workspace_service = WorkspaceService(workspace_repository=workspace_repository)

    auth_service = AuthService(
        user_repository=user_repository,
        secret_key=settings.auth_secret_key,
        token_expire_minutes=settings.auth_token_expire_minutes,
        registration_enabled=settings.enable_registration,
        password_reset_expire_minutes=settings.password_reset_expire_minutes,
        password_reset_frontend_url=settings.password_reset_frontend_url,
        oauth_google_client_id=settings.oauth_google_client_id,
        oauth_google_client_secret=settings.oauth_google_client_secret,
        oauth_github_client_id=settings.oauth_github_client_id,
        oauth_github_client_secret=settings.oauth_github_client_secret,
        oauth_allowed_redirect_base=settings.oauth_allowed_redirect_base,
    )

    return AppContainer(
        ingestion_service=ingestion_service,
        question_answering_service=question_answering_service,
        auth_service=auth_service,
        rate_limiter=rate_limiter,
        runtime_metrics=runtime_metrics,
        vector_store_repository=vector_store_repository,
        vector_store_admin_service=vector_store_admin_service,
        workspace_service=workspace_service,
    )
