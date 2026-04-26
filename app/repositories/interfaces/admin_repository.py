from abc import ABC, abstractmethod

from app.models.entities import AuditLogEntry


class IAdminRepository(ABC):
    @abstractmethod
    def get_stats(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def count_users(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def count_chats(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def count_documents(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def count_messages(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def count_recent_users(self, days: int = 7) -> int:
        raise NotImplementedError

    @abstractmethod
    def top_users_by_messages(self, limit: int = 10) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def messages_per_day(self, days: int = 30) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def add_audit_log(self, entry: AuditLogEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_audit_logs(self, offset: int = 0, limit: int = 50) -> list[AuditLogEntry]:
        raise NotImplementedError

    @abstractmethod
    def count_audit_logs(self) -> int:
        raise NotImplementedError
