from abc import ABC, abstractmethod

from app.models.entities import AuditLogEntry, UserAccount


class IAdminService(ABC):
    @abstractmethod
    def get_dashboard_stats(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_users(self, offset: int = 0, limit: int = 50) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_user_detail(self, username: str) -> UserAccount:
        raise NotImplementedError

    @abstractmethod
    def update_user_role(self, admin_username: str, target_username: str, role: str) -> UserAccount:
        raise NotImplementedError

    @abstractmethod
    def update_user_status(self, admin_username: str, target_username: str, is_active: bool) -> UserAccount:
        raise NotImplementedError

    @abstractmethod
    def delete_user(self, admin_username: str, target_username: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def admin_reset_password(self, admin_username: str, target_username: str, new_password: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_system_metrics(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_system_config(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_audit_logs(self, offset: int = 0, limit: int = 50) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_usage_analytics(self, days: int = 30) -> dict:
        raise NotImplementedError

    @abstractmethod
    def setup_first_admin(self, username: str, password: str) -> UserAccount:
        raise NotImplementedError
