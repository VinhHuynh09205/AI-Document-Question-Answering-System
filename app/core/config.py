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
    local_semantic_embeddings: bool = False
    local_semantic_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    local_semantic_normalize_embeddings: bool = True

    vector_store_path: str = "data/faiss_index"
    vector_backup_dir: str = "data/faiss_backups"
    upload_dir: str = "data/uploads"
    database_backend: str = "sqlite"
    database_path: str = "data/app.db"
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "aichatbox"
    mysql_user: str = "aichatbox"
    mysql_password: str = "aichatbox"
    mysql_charset: str = "utf8mb4"
    users_file_path: str = "data/users.json"
    supported_upload_extensions: str = ".pdf,.doc,.docx,.xlsx,.xls,.pptx,.html,.htm,.json,.xml,.txt,.md,.csv"
    replace_existing_documents_on_upload: bool = True

    auth_secret_key: str = "change-me-in-production"
    auth_token_expire_minutes: int = 60
    enable_registration: bool = True
    password_reset_expire_minutes: int = 20
    password_reset_frontend_url: str = "http://localhost:8000/login"
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    oauth_github_client_id: str = ""
    oauth_github_client_secret: str = ""
    oauth_allowed_redirect_base: str = "http://localhost:8000"

    chunk_size: int = 1500
    chunk_overlap: int = 200
    top_k: int = 6
    min_context_token_overlap: float = 0.15
    min_relevant_chunks: int = 1
    max_answer_chars: int = 2500
    qa_cache_ttl_seconds: int = 300
    qa_cache_max_size: int = 128
    log_level: str = "INFO"
    rate_limit_window_seconds: int = 60
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
            "ask": self.ask_rate_limit_per_window,
            "upload": self.upload_rate_limit_per_window,
        }

    def get_cors_allow_origins(self) -> list[str]:
        return self._split_csv(self.cors_allow_origins)

    def get_cors_allow_methods(self) -> list[str]:
        return self._split_csv(self.cors_allow_methods)

    def get_cors_allow_headers(self) -> list[str]:
        return self._split_csv(self.cors_allow_headers)

    def get_database_backend(self) -> str:
        return self.database_backend.strip().lower() or "sqlite"

    @staticmethod
    def _split_csv(raw_value: str) -> list[str]:
        return [token.strip() for token in raw_value.split(",") if token.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
