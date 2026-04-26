from abc import ABC, abstractmethod

from app.models.entities import UserAccount


class IUserRepository(ABC):
    @abstractmethod
    def get_by_username(self, username: str) -> UserAccount | None:
        raise NotImplementedError

    @abstractmethod
    def add(self, user: UserAccount) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_password_hash(self, username: str, password_hash: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_all(self, offset: int = 0, limit: int = 50) -> list[UserAccount]:
        raise NotImplementedError

    @abstractmethod
    def count_all(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def update_role(self, username: str, role: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def update_active(self, username: str, is_active: bool) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete(self, username: str) -> bool:
        raise NotImplementedError
