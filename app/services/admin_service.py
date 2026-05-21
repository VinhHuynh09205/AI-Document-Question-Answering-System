import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.models.entities import AuditLogEntry, UserAccount
from app.repositories.interfaces.admin_repository import IAdminRepository
from app.repositories.interfaces.user_repository import IUserRepository
from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.interfaces.admin_service import IAdminService
from app.services.interfaces.runtime_metrics import IRuntimeMetrics
from app.services.interfaces.workspace_service import IWorkspaceService


class AdminService(IAdminService):
    def __init__(
        self,
        user_repository: IUserRepository,
        admin_repository: IAdminRepository,
        vector_store_repository: IVectorStoreRepository,
        workspace_service: IWorkspaceService,
        runtime_metrics: IRuntimeMetrics,
        settings: Settings,
        hash_password_fn,
    ) -> None:
        self._user_repository = user_repository
        self._admin_repository = admin_repository
        self._vector_store_repository = vector_store_repository
        self._workspace_service = workspace_service
        self._runtime_metrics = runtime_metrics
        self._settings = settings
        self._hash_password = hash_password_fn

    def get_dashboard_stats(self) -> dict:
        stats = self._admin_repository.get_stats()
        recent_users = self._admin_repository.count_recent_users(days=7)
        vector_count = self._vector_store_repository.document_count()
        metrics = self._runtime_metrics.snapshot()

        return {
            **stats,
            "recent_registrations_7d": recent_users,
            "vector_store_documents": vector_count,
            "uptime_seconds": metrics.get("uptime_seconds", 0),
            "total_requests": metrics.get("total_requests", 0),
            "fallback_answers": metrics.get("fallback_answers", 0),
            "rate_limited_requests": metrics.get("rate_limited_requests", 0),
        }

    def list_users(self, offset: int = 0, limit: int = 50) -> dict:
        users = self._user_repository.list_all(offset=offset, limit=limit)
        total = self._user_repository.count_all()
        return {
            "users": [
                {
                    "username": u.username,
                    "role": u.role,
                    "is_active": u.is_active,
                    "created_at": u.created_at,
                }
                for u in users
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def get_user_detail(self, username: str) -> UserAccount:
        user = self._user_repository.get_by_username(username)
        if user is None:
            raise ValueError("User not found")
        return user

    def update_user_role(
        self,
        admin_username: str,
        target_username: str,
        role: str,
        audit_context: dict[str, str] | None = None,
    ) -> UserAccount:
        normalized_role = role.strip().lower()
        if normalized_role not in ("user", "admin"):
            raise ValueError("Invalid role. Must be 'user' or 'admin'")

        user = self._user_repository.get_by_username(target_username)
        if user is None:
            raise ValueError("User not found")

        if user.role == "admin" and normalized_role != "admin" and self._count_admin_users() <= 1:
            raise ValueError("Cannot demote the last admin account")

        old_role = user.role
        self._user_repository.update_role(target_username, normalized_role)
        self._audit(
            admin_username,
            "update_role",
            target_username,
            f"old_role={old_role}; new_role={normalized_role}",
            audit_context,
        )

        user = self._user_repository.get_by_username(target_username)
        return user

    def update_user_status(
        self,
        admin_username: str,
        target_username: str,
        is_active: bool,
        audit_context: dict[str, str] | None = None,
    ) -> UserAccount:
        user = self._user_repository.get_by_username(target_username)
        if user is None:
            raise ValueError("User not found")

        if user.role == "admin" and user.is_active and not is_active and self._count_active_admin_users() <= 1:
            raise ValueError("Cannot deactivate the last active admin account")

        old_status = "active" if user.is_active else "inactive"
        self._user_repository.update_active(target_username, is_active)
        status_label = "activated" if is_active else "deactivated"
        self._audit(
            admin_username,
            "update_status",
            target_username,
            f"old_status={old_status}; new_status={status_label}",
            audit_context,
        )

        user = self._user_repository.get_by_username(target_username)
        return user

    def delete_user(
        self,
        admin_username: str,
        target_username: str,
        audit_context: dict[str, str] | None = None,
    ) -> bool:
        user = self._user_repository.get_by_username(target_username)
        if user is None:
            raise ValueError("User not found")

        canonical_username = user.username

        if canonical_username.strip().lower() == admin_username.strip().lower():
            raise ValueError("Cannot delete yourself")

        if user.role == "admin" and self._count_admin_users() <= 1:
            raise ValueError("Cannot delete the last admin account")

        cleanup = self._cleanup_user_workspace(canonical_username)
        deleted = self._user_repository.delete(canonical_username)
        if deleted:
            detail = (
                "deleted"
                f"; chats={cleanup['chats_deleted']}"
                f"; documents={cleanup['documents_deleted']}"
                f"; vector_chunks={cleanup['vector_chunks_deleted']}"
                f"; files={cleanup['files_deleted']}"
            )
            self._audit(admin_username, "delete_user", canonical_username, detail, audit_context)
        return deleted

    def admin_reset_password(
        self,
        admin_username: str,
        target_username: str,
        new_password: str,
        audit_context: dict[str, str] | None = None,
    ) -> bool:
        user = self._user_repository.get_by_username(target_username)
        if user is None:
            raise ValueError("User not found")

        password_hash = self._hash_password(new_password)
        updated = self._user_repository.update_password_hash(target_username, password_hash)
        if updated:
            self._audit(
                admin_username,
                "reset_password",
                target_username,
                "password_reset_by_admin",
                audit_context,
            )
        return updated

    def get_system_metrics(self) -> dict:
        return self._runtime_metrics.snapshot()

    def get_system_config(self) -> dict:
        s = self._settings
        effective_extensions = ",".join(sorted(s.get_supported_upload_extensions()))
        return {
            "app_name": s.app_name,
            "app_env": s.app_env,
            "database_backend": "postgresql",
            "openai_model": s.openai_model,
            "gemini_model": s.gemini_model,
            "groq_model": s.groq_model,
            "embeddings_model": s.embeddings_model,
            "local_semantic_embeddings": s.local_semantic_embeddings,
            "chunk_size": s.chunk_size,
            "chunk_overlap": s.chunk_overlap,
            "top_k": s.top_k,
            "max_answer_chars": s.max_answer_chars,
            "rate_limit_window_seconds": s.rate_limit_window_seconds,
            "ask_rate_limit_per_window": s.ask_rate_limit_per_window,
            "upload_rate_limit_per_window": s.upload_rate_limit_per_window,
            "enable_registration": s.enable_registration,
            "enable_security_headers": s.enable_security_headers,
            "supported_upload_extensions": effective_extensions,
            "has_openai_key": bool(s.openai_api_key),
            "has_google_key": bool(s.google_api_key),
            "has_groq_key": bool(s.groq_api_key),
            "has_oauth_google": bool(s.oauth_google_client_id),
            "has_oauth_github": bool(s.oauth_github_client_id),
            "auth_secret_configured": bool(
                s.auth_secret_key.strip()
                and s.auth_secret_key.strip() != "change-me-in-production"
            ),
            "admin_setup_enabled": bool(s.admin_setup_secret.strip()),
        }

    def list_audit_logs(self, offset: int = 0, limit: int = 50) -> dict:
        logs = self._admin_repository.list_audit_logs(offset=offset, limit=limit)
        total = self._admin_repository.count_audit_logs()
        return {
            "logs": [
                {
                    "log_id": log.log_id,
                    "admin_username": log.admin_username,
                    "action": log.action,
                    "target": log.target,
                    "detail": log.detail,
                    "created_at": log.created_at,
                    "ip_address": log.ip_address,
                    "user_agent": log.user_agent,
                    "request_id": log.request_id,
                }
                for log in logs
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def get_usage_analytics(self, days: int = 30) -> dict:
        top_users = self._admin_repository.top_users_by_messages(limit=10)
        daily_messages = self._admin_repository.messages_per_day(days=days)
        return {
            "top_users": top_users,
            "messages_per_day": daily_messages,
            "period_days": days,
        }

    def setup_first_admin(
        self,
        username: str,
        password: str,
        audit_context: dict[str, str] | None = None,
    ) -> UserAccount:
        if self._count_admin_users() > 0:
            raise ValueError("Admin account already exists")

        existing = self._user_repository.get_by_username(username)
        if existing is not None:
            self._user_repository.update_role(username, "admin")
            self._audit(
                username,
                "setup_first_admin",
                username,
                "promoted_existing_user",
                audit_context,
            )
            return self._user_repository.get_by_username(username)

        password_hash = self._hash_password(password)
        new_user = UserAccount(
            username=username.strip().lower(),
            password_hash=password_hash,
            role="admin",
            is_active=True,
        )
        self._user_repository.add(new_user)
        self._audit(username, "setup_first_admin", username, "created_new_admin", audit_context)
        return self._user_repository.get_by_username(username)

    def _list_all_users(self) -> list[UserAccount]:
        total = max(1, self._user_repository.count_all())
        return self._user_repository.list_all(offset=0, limit=total)

    def _count_admin_users(self) -> int:
        return sum(1 for user in self._list_all_users() if user.role == "admin")

    def _count_active_admin_users(self) -> int:
        return sum(1 for user in self._list_all_users() if user.role == "admin" and user.is_active)

    def _cleanup_user_workspace(self, username: str) -> dict[str, int]:
        documents = []
        chats = self._workspace_service.list_chats(username)
        for chat in chats:
            documents.extend(self._workspace_service.list_documents(username, chat.chat_id))

        removed_chunks = self._vector_store_repository.delete_documents_by_metadata({"owner": username})
        if removed_chunks > 0:
            self._vector_store_repository.save()

        deleted_chats = 0
        for chat in chats:
            if self._workspace_service.delete_chat(username, chat.chat_id):
                deleted_chats += 1

        deleted_files = 0
        for document in documents:
            if not document.stored_path:
                continue
            try:
                path = Path(document.stored_path)
                existed = path.exists()
                path.unlink(missing_ok=True)
                if existed:
                    deleted_files += 1
            except OSError:
                # File cleanup must not leave the user account half-deleted.
                continue

        return {
            "chats_deleted": deleted_chats,
            "documents_deleted": len(documents),
            "vector_chunks_deleted": max(0, int(removed_chunks)),
            "files_deleted": deleted_files,
        }

    def _audit(
        self,
        admin_username: str,
        action: str,
        target: str,
        detail: str,
        context: dict[str, str] | None = None,
    ) -> None:
        safe_context = context or {}
        entry = AuditLogEntry(
            log_id=uuid.uuid4().hex,
            admin_username=admin_username,
            action=action,
            target=target,
            detail=detail,
            created_at=datetime.now(UTC).isoformat(),
            ip_address=str(safe_context.get("ip_address", ""))[:64],
            user_agent=str(safe_context.get("user_agent", ""))[:512],
            request_id=str(safe_context.get("request_id", ""))[:128],
        )
        self._admin_repository.add_audit_log(entry)
