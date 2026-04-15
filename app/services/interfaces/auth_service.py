from abc import ABC, abstractmethod

from app.models.entities import AuthTokenResult


class IAuthService(ABC):
    @abstractmethod
    def register(self, username: str, password: str) -> AuthTokenResult:
        raise NotImplementedError

    @abstractmethod
    def login(self, username: str, password: str) -> AuthTokenResult:
        raise NotImplementedError
