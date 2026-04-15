from dataclasses import dataclass, field


@dataclass(slots=True)
class UploadResult:
    files_processed: int
    chunks_indexed: int


@dataclass(slots=True)
class AnswerResult:
    answer: str
    sources: list[str] = field(default_factory=list)
    context_found: bool = False


@dataclass(slots=True)
class UserAccount:
    username: str
    password_hash: str


@dataclass(slots=True)
class AuthTokenResult:
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 0


@dataclass(slots=True)
class ChatSession:
    chat_id: str
    username: str
    title: str
    created_at: str


@dataclass(slots=True)
class StoredDocument:
    document_id: str
    chat_id: str
    username: str
    original_name: str
    stored_path: str
    created_at: str


@dataclass(slots=True)
class ChatMessage:
    message_id: str
    chat_id: str
    username: str
    role: str
    content: str
    created_at: str
