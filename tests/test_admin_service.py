from pathlib import Path

import pytest

from app.core.config import Settings
from app.models.entities import AuditLogEntry, ChatSession, StoredDocument, UserAccount
from app.services.admin_service import AdminService


class _UserRepo:
    def __init__(self, users: list[UserAccount]) -> None:
        self.users = {user.username: user for user in users}

    def get_by_username(self, username: str) -> UserAccount | None:
        normalized = username.strip().lower()
        for user in self.users.values():
            if user.username.lower() == normalized:
                return user
        return None

    def list_all(self, offset: int = 0, limit: int = 50) -> list[UserAccount]:
        return list(self.users.values())[offset: offset + limit]

    def count_all(self) -> int:
        return len(self.users)

    def update_role(self, username: str, role: str) -> bool:
        user = self.get_by_username(username)
        if user is None:
            return False
        user.role = role
        return True

    def update_active(self, username: str, is_active: bool) -> bool:
        user = self.get_by_username(username)
        if user is None:
            return False
        user.is_active = is_active
        return True

    def update_password_hash(self, username: str, password_hash: str) -> bool:
        user = self.get_by_username(username)
        if user is None:
            return False
        user.password_hash = password_hash
        return True

    def delete(self, username: str) -> bool:
        user = self.get_by_username(username)
        if user is None:
            return False
        del self.users[user.username]
        return True

    def add(self, user: UserAccount) -> None:
        self.users[user.username] = user


class _AdminRepo:
    def __init__(self) -> None:
        self.logs: list[AuditLogEntry] = []

    def get_stats(self) -> dict:
        return {"total_users": 0, "total_chats": 0, "total_documents": 0, "total_messages": 0}

    def count_recent_users(self, days: int = 7) -> int:
        return 0

    def top_users_by_messages(self, limit: int = 10) -> list[dict]:
        return []

    def messages_per_day(self, days: int = 30) -> list[dict]:
        return []

    def add_audit_log(self, entry: AuditLogEntry) -> None:
        self.logs.append(entry)

    def list_audit_logs(self, offset: int = 0, limit: int = 50) -> list[AuditLogEntry]:
        return self.logs[offset: offset + limit]

    def count_audit_logs(self) -> int:
        return len(self.logs)


class _VectorStore:
    def __init__(self, removed_count: int = 0) -> None:
        self.removed_count = removed_count
        self.deleted_filters: list[dict] = []
        self.saved = False

    def document_count(self) -> int:
        return 0

    def delete_documents_by_metadata(self, metadata_filter: dict[str, str | list[str]]) -> int:
        self.deleted_filters.append(metadata_filter)
        return self.removed_count

    def save(self) -> None:
        self.saved = True


class _RuntimeMetrics:
    def snapshot(self) -> dict:
        return {
            "uptime_seconds": 0,
            "total_requests": 0,
            "fallback_answers": 0,
            "rate_limited_requests": 0,
        }


class _WorkspaceService:
    def __init__(self, docs: list[StoredDocument]) -> None:
        self.docs = docs
        self.deleted_chats: list[str] = []

    def list_chats(self, username: str) -> list[ChatSession]:
        chat_ids = sorted({doc.chat_id for doc in self.docs if doc.username == username})
        return [ChatSession(chat_id=chat_id, username=username, title="Chat", created_at="") for chat_id in chat_ids]

    def list_documents(self, username: str, chat_id: str) -> list[StoredDocument]:
        return [doc for doc in self.docs if doc.username == username and doc.chat_id == chat_id]

    def delete_chat(self, username: str, chat_id: str) -> bool:
        self.deleted_chats.append(chat_id)
        self.docs = [doc for doc in self.docs if not (doc.username == username and doc.chat_id == chat_id)]
        return True


def _service(
    *,
    user_repo: _UserRepo,
    admin_repo: _AdminRepo | None = None,
    vector_store: _VectorStore | None = None,
    workspace_service: _WorkspaceService | None = None,
    settings: Settings | None = None,
) -> AdminService:
    return AdminService(
        user_repository=user_repo,
        admin_repository=admin_repo or _AdminRepo(),
        vector_store_repository=vector_store or _VectorStore(),
        workspace_service=workspace_service or _WorkspaceService([]),
        runtime_metrics=_RuntimeMetrics(),
        settings=settings or Settings(auth_secret_key="test-secret"),
        hash_password_fn=lambda password: f"hash:{password}",
    )


def test_delete_user_cleans_workspace_vectors_files_and_audits_context(tmp_path: Path) -> None:
    stored_file = tmp_path / "report.pdf"
    stored_file.write_text("content", encoding="utf-8")
    user_repo = _UserRepo([
        UserAccount(username="admin", password_hash="x", role="admin"),
        UserAccount(username="bob", password_hash="x", role="user"),
    ])
    admin_repo = _AdminRepo()
    vector_store = _VectorStore(removed_count=3)
    workspace_service = _WorkspaceService([
        StoredDocument(
            document_id="doc-1",
            chat_id="chat-1",
            username="bob",
            original_name="report.pdf",
            stored_path=str(stored_file),
            created_at="",
        )
    ])
    service = _service(
        user_repo=user_repo,
        admin_repo=admin_repo,
        vector_store=vector_store,
        workspace_service=workspace_service,
    )

    deleted = service.delete_user(
        "admin",
        "bob",
        audit_context={
            "ip_address": "127.0.0.1",
            "user_agent": "pytest",
            "request_id": "req-1",
        },
    )

    assert deleted is True
    assert user_repo.get_by_username("bob") is None
    assert vector_store.deleted_filters == [{"owner": "bob"}]
    assert vector_store.saved is True
    assert workspace_service.deleted_chats == ["chat-1"]
    assert not stored_file.exists()
    assert len(admin_repo.logs) == 1
    log = admin_repo.logs[0]
    assert log.action == "delete_user"
    assert log.target == "bob"
    assert "chats=1" in log.detail
    assert "documents=1" in log.detail
    assert "vector_chunks=3" in log.detail
    assert log.ip_address == "127.0.0.1"
    assert log.user_agent == "pytest"
    assert log.request_id == "req-1"


def test_delete_user_refuses_last_admin_before_cleanup() -> None:
    user_repo = _UserRepo([UserAccount(username="admin", password_hash="x", role="admin")])
    vector_store = _VectorStore(removed_count=1)
    workspace_service = _WorkspaceService([
        StoredDocument(
            document_id="doc-1",
            chat_id="chat-1",
            username="admin",
            original_name="report.pdf",
            stored_path="missing.pdf",
            created_at="",
        )
    ])
    service = _service(
        user_repo=user_repo,
        vector_store=vector_store,
        workspace_service=workspace_service,
    )

    with pytest.raises(ValueError, match="Cannot delete the last admin account"):
        service.delete_user("other-admin", "admin")

    assert user_repo.get_by_username("admin") is not None
    assert vector_store.deleted_filters == []
    assert workspace_service.deleted_chats == []


def test_system_config_marks_default_auth_secret_as_unconfigured() -> None:
    service = _service(
        user_repo=_UserRepo([]),
        settings=Settings(auth_secret_key="change-me-in-production", admin_setup_secret="setup"),
    )

    config = service.get_system_config()

    assert config["auth_secret_configured"] is False
    assert config["admin_setup_enabled"] is True
