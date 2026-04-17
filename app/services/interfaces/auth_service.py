from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.entities import AuthTokenResult


@dataclass(slots=True)
class OAuthStartResult:
    authorization_url: str
    state: str


@dataclass(slots=True)
class ForgotPasswordResult:
    message: str
    reset_token: str | None = None
    reset_url: str | None = None


class IAuthService(ABC):
    @abstractmethod
    def register(self, username: str, password: str) -> AuthTokenResult:
        raise NotImplementedError

    @abstractmethod
    def login(self, username: str, password: str) -> AuthTokenResult:
        raise NotImplementedError

    @abstractmethod
    def forgot_password(self, username: str, redirect_uri: str) -> ForgotPasswordResult:
        raise NotImplementedError

    @abstractmethod
    def reset_password(self, token: str, new_password: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def build_oauth_start_url(self, provider: str, redirect_uri: str) -> OAuthStartResult:
        raise NotImplementedError

    @abstractmethod
    def complete_oauth_login(
        self,
        provider: str,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> tuple[str, AuthTokenResult]:
        raise NotImplementedError
