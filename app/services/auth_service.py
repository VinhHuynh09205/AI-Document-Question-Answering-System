import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.models.entities import AuthTokenResult, UserAccount
from app.repositories.interfaces.user_repository import IUserRepository
from app.services.auth_exceptions import (
    InvalidCredentialsError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
)
from app.services.interfaces.auth_service import IAuthService

PBKDF2_ITERATIONS = 390000
JWT_ALGORITHM = "HS256"


class AuthService(IAuthService):
    def __init__(
        self,
        user_repository: IUserRepository,
        secret_key: str,
        token_expire_minutes: int,
        registration_enabled: bool,
    ) -> None:
        self._user_repository = user_repository
        self._secret_key = secret_key
        self._token_expire_minutes = token_expire_minutes
        self._registration_enabled = registration_enabled

    def register(self, username: str, password: str) -> AuthTokenResult:
        if not self._registration_enabled:
            raise RegistrationDisabledError("Registration is disabled")

        normalized_username = username.strip()
        existing = self._user_repository.get_by_username(normalized_username)
        if existing is not None:
            raise UserAlreadyExistsError("Username already exists")

        password_hash = self._hash_password(password)
        self._user_repository.add(
            UserAccount(username=normalized_username, password_hash=password_hash)
        )

        return self._create_token(normalized_username)

    def login(self, username: str, password: str) -> AuthTokenResult:
        normalized_username = username.strip()
        user = self._user_repository.get_by_username(normalized_username)
        if user is None:
            raise InvalidCredentialsError("Invalid username or password")

        if not self._verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid username or password")

        return self._create_token(user.username)

    def _create_token(self, username: str) -> AuthTokenResult:
        expires_delta = timedelta(minutes=self._token_expire_minutes)
        expiration = datetime.now(UTC) + expires_delta
        payload = {
            "sub": username,
            "exp": expiration,
        }
        token = jwt.encode(payload, self._secret_key, algorithm=JWT_ALGORITHM)

        return AuthTokenResult(
            access_token=token,
            token_type="bearer",
            expires_in=int(expires_delta.total_seconds()),
        )

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS,
        )
        salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
        digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
        return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"

    @staticmethod
    def _verify_password(password: str, password_hash: str) -> bool:
        try:
            algorithm, iterations_str, salt_b64, digest_b64 = password_hash.split("$")
        except ValueError:
            return False

        if algorithm != "pbkdf2_sha256":
            return False

        iterations = int(iterations_str)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual_digest, expected_digest)
