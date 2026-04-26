from pydantic import BaseModel, Field


class DashboardStatsResponse(BaseModel):
    total_users: int
    total_chats: int
    total_documents: int
    total_messages: int
    recent_registrations_7d: int
    vector_store_documents: int
    uptime_seconds: int
    total_requests: int
    fallback_answers: int
    rate_limited_requests: int


class AdminUserResponse(BaseModel):
    username: str
    role: str
    is_active: bool
    created_at: str


class AdminUserListResponse(BaseModel):
    users: list[AdminUserResponse]
    total: int
    offset: int
    limit: int


class SetupFirstAdminRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(user|admin)$")


class UpdateStatusRequest(BaseModel):
    is_active: bool


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)


class SystemMetricsResponse(BaseModel):
    uptime_seconds: int
    total_requests: int
    status_counts: dict[str, int]
    endpoint_counts: dict[str, int]
    fallback_answers: int
    rate_limited_requests: int


class SystemConfigResponse(BaseModel):
    app_name: str
    app_env: str
    database_backend: str
    openai_model: str
    gemini_model: str
    groq_model: str
    embeddings_model: str
    local_semantic_embeddings: bool
    chunk_size: int
    chunk_overlap: int
    top_k: int
    max_answer_chars: int
    rate_limit_window_seconds: int
    ask_rate_limit_per_window: int
    upload_rate_limit_per_window: int
    enable_registration: bool
    enable_security_headers: bool
    supported_upload_extensions: str
    has_openai_key: bool
    has_google_key: bool
    has_groq_key: bool
    has_oauth_google: bool
    has_oauth_github: bool


class AuditLogEntryResponse(BaseModel):
    log_id: str
    admin_username: str
    action: str
    target: str
    detail: str
    created_at: str


class AuditLogListResponse(BaseModel):
    logs: list[AuditLogEntryResponse]
    total: int
    offset: int
    limit: int


class TopUserResponse(BaseModel):
    username: str
    message_count: int


class DailyMessageResponse(BaseModel):
    date: str
    count: int


class UsageAnalyticsResponse(BaseModel):
    top_users: list[TopUserResponse]
    messages_per_day: list[DailyMessageResponse]
    period_days: int
