from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    message: str
    files_processed: int
    chunks_indexed: int
    original_names: list[str] = Field(default_factory=list)
    job_id: str | None = None
    status: str | None = None
    status_url: str | None = None


class UploadJobStatusResponse(BaseModel):
    job_id: str
    chat_id: str
    status: str
    stage: str
    progress: int = Field(ge=0, le=100)
    files_total: int = Field(ge=0)
    files_processed: int = Field(ge=0)
    chunks_total: int = Field(ge=0)
    chunks_indexed: int = Field(ge=0)
    original_names: list[str] = Field(default_factory=list)
    message: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    top_k: int | None = Field(default=None, ge=1, le=20, description="Number of chunks to retrieve")
    selected_document_ids: list[str] = Field(
        default_factory=list,
        description="Explicit document IDs to scope retrieval in workspace ask endpoints",
    )


class AskResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool]


class MetricsResponse(BaseModel):
    uptime_seconds: int
    total_requests: int
    status_counts: dict[str, int]
    endpoint_counts: dict[str, int]
    fallback_answers: int
    rate_limited_requests: int


class VectorStoreStatusResponse(BaseModel):
    document_count: int
    backup_root_dir: str


class VectorStoreBackupResponse(BaseModel):
    backup_name: str | None = None
    backup_dir: str | None = None
    backed_up: bool | None = None
    restored: bool | None = None
    cleared: bool | None = None
    reason: str | None = None
    document_count: int


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    username: str | None = None
    role: str = "user"


class ForgotPasswordRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    redirect_uri: str | None = Field(default=None, min_length=1, max_length=512)


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None
    reset_url: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=4096)
    new_password: str = Field(..., min_length=8, max_length=128)


class OAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthCompleteRequest(BaseModel):
    code: str = Field(..., min_length=5, max_length=4096)
    state: str = Field(..., min_length=8, max_length=256)
    redirect_uri: str | None = Field(default=None, min_length=1, max_length=512)


class CreateChatRequest(BaseModel):
    title: str = Field(default="Đoạn chat mới", min_length=1, max_length=200)


class RenameChatRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class RenameDocumentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ChatResponse(BaseModel):
    chat_id: str
    title: str
    created_at: str


class ChatListResponse(BaseModel):
    chats: list[ChatResponse]


class DocumentRecordResponse(BaseModel):
    document_id: str
    original_name: str
    stored_path: str
    created_at: str
    upload_index: int | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentRecordResponse]


class MessageRecordResponse(BaseModel):
    message_id: str
    role: str
    content: str
    created_at: str


class MessageListResponse(BaseModel):
    messages: list[MessageRecordResponse]
