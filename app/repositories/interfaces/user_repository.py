from abc import ABC, abstractmethod

from app.models.entities import UserAccount


class IUserRepository(ABC):
    @abstractmethod
    def get_by_username(self, username: str) -> UserAccount | None:
        raise NotImplementedError

    @abstractmethod
    def add(self, user: UserAccount) -> None:
        raise NotImplementedError
