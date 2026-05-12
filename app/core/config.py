from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AIChatBox"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    embeddings_model: str = "text-embedding-3-small"
    local_semantic_embeddings_enabled: bool = False
    local_semantic_embeddings: bool = False
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    local_semantic_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    local_semantic_normalize_embeddings: bool = True
    embedding_device: str = "auto"
    embedding_cache_enabled: bool = True
    hybrid_retrieval_enabled: bool = True
    reranking_enabled: bool = True

    vector_store_path: str = "data/faiss_index"
    vector_backup_dir: str = "data/faiss_backups"
    upload_dir: str = "data/uploads"
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "aichatbox"
    pg_user: str = "aichatbox"
    pg_password: str = "aichatbox"
    users_file_path: str = "data/users.json"
    supported_upload_extensions: str = ".pdf,.doc,.docx,.xlsx,.xls,.pptx,.html,.htm,.json,.xml,.txt,.md,.csv,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.gif"
    replace_existing_documents_on_upload: bool = True
    allow_duplicate_keep_both_uploads: bool = True

    enable_image_understanding: bool = True
    enable_gemini_image_understanding: bool = True
    gemini_vision_model: str = "gemini-2.0-flash"
    enable_local_vision_fallback: bool = True
    local_vision_endpoint: str = "http://localhost:11434"
    local_vision_model: str = "llava:7b"
    local_vision_model_candidates: str = "qwen2.5vl:7b,llava:13b,llava:7b"
    local_vision_model_discovery_ttl_seconds: int = 300
    local_vision_max_model_attempts: int = 1
    local_vision_request_timeout_seconds: float = 8.0
    local_vision_max_concurrency: int = 1
    enable_local_ocr_fallback: bool = True
    local_ocr_max_concurrency: int = 1
    image_understanding_min_bytes: int = 2048
    image_understanding_min_edge_pixels: int = 96
    image_ocr_min_confidence: float = 0.35
    ocr_max_variants_per_image: int = 2
    ocr_max_seconds_per_image: float = 6.0
    image_analysis_max_concurrency: int = 2
    image_analysis_timeout_seconds: float = 25.0
    image_analysis_max_lines: int = 12
    image_analysis_min_meaningful_chars: int = 10
    image_analysis_min_area_pixels: int = 14400
    image_analysis_min_entropy: float = 2.2
    image_analysis_min_text_density: float = 0.015
    image_analysis_max_pixels: int = 2200000
    image_analysis_min_edge_mean: float = 3.0
    image_analysis_min_grayscale_stddev: float = 6.0

    pdf_max_images_per_page: int = 2
    pdf_max_pages_with_image_analysis: int = 12
    pdf_image_analysis_text_char_threshold: int = 900
    pdf_image_analysis_max_seconds_per_document: float = 20.0

    docx_max_images_per_document: int = 4
    docx_image_analysis_text_char_threshold: int = 2200
    docx_image_analysis_max_seconds_per_document: float = 20.0

    pptx_max_images_per_slide: int = 2
    pptx_max_images_per_document: int = 24
    pptx_max_slides_with_image_analysis: int = 12
    pptx_image_analysis_text_char_threshold: int = 950
    pptx_image_analysis_max_seconds_per_document: float = 25.0

    auth_secret_key: str = "change-me-in-production"
    admin_setup_secret: str = ""
    auth_token_expire_minutes: int = 60
    enable_registration: bool = True
    password_reset_expire_minutes: int = 20
    password_reset_frontend_url: str = "http://localhost:8000/login"
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    oauth_github_client_id: str = ""
    oauth_github_client_secret: str = ""
    oauth_allowed_redirect_base: str = "http://localhost:8000"

    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 6
    min_context_token_overlap: float = 0.15
    min_relevant_chunks: int = 1
    max_answer_chars: int = 2500
    qa_cache_ttl_seconds: int = 300
    qa_cache_max_size: int = 128
    ingestion_max_file_workers: int = 4
    embedding_batch_size: int = 64
    upload_job_retention_seconds: int = 3600
    upload_job_max_retries: int = 3
    upload_job_worker_poll_seconds: float = 0.8
    upload_job_stale_processing_seconds: int = 120
    log_level: str = "INFO"
    rate_limit_window_seconds: int = 60
    login_rate_limit_per_window: int = 20
    register_rate_limit_per_window: int = 10
    ask_rate_limit_per_window: int = 60
    upload_rate_limit_per_window: int = 30
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "GET,POST,OPTIONS"
    cors_allow_headers: str = "*"
    enable_security_headers: bool = True
    enable_hsts: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_supported_upload_extensions(self) -> set[str]:
        tokens = self.supported_upload_extensions.split(",")
        return {
            f".{token.strip().lower().lstrip('.')}"
            for token in tokens
            if token.strip()
        }

    def get_rate_limit_config(self) -> dict[str, int]:
        return {
            "login": self.login_rate_limit_per_window,
            "register": self.register_rate_limit_per_window,
            "ask": self.ask_rate_limit_per_window,
            "upload": self.upload_rate_limit_per_window,
        }

    def use_local_semantic_embeddings(self) -> bool:
        return bool(self.local_semantic_embeddings_enabled or self.local_semantic_embeddings)

    def get_local_embedding_model(self) -> str:
        preferred = str(self.local_embedding_model or "").strip()
        if preferred:
            return preferred
        return str(self.local_semantic_model_name or "").strip()

    def get_cors_allow_origins(self) -> list[str]:
        return self._split_csv(self.cors_allow_origins)

    def get_cors_allow_methods(self) -> list[str]:
        return self._split_csv(self.cors_allow_methods)

    def get_cors_allow_headers(self) -> list[str]:
        return self._split_csv(self.cors_allow_headers)

    @staticmethod
    def _split_csv(raw_value: str) -> list[str]:
        return [token.strip() for token in raw_value.split(",") if token.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
