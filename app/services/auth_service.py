import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

import jwt

from app.models.entities import AuthTokenResult, UserAccount
from app.repositories.interfaces.user_repository import IUserRepository
from app.services.auth_exceptions import (
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    OAuthConfigurationError,
    OAuthProviderNotSupportedError,
    OAuthStateInvalidError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
)
from app.services.interfaces.auth_service import ForgotPasswordResult, IAuthService, OAuthStartResult

PBKDF2_ITERATIONS = 390000
JWT_ALGORITHM = "HS256"
OAUTH_STATE_EXPIRE_MINUTES = 10

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USERINFO_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


class AuthService(IAuthService):
    def __init__(
        self,
        user_repository: IUserRepository,
        secret_key: str,
        token_expire_minutes: int,
        registration_enabled: bool,
        password_reset_expire_minutes: int,
        password_reset_frontend_url: str,
        oauth_google_client_id: str,
        oauth_google_client_secret: str,
        oauth_github_client_id: str,
        oauth_github_client_secret: str,
        oauth_allowed_redirect_base: str,
    ) -> None:
        self._user_repository = user_repository
        self._secret_key = secret_key
        self._token_expire_minutes = token_expire_minutes
        self._registration_enabled = registration_enabled
        self._password_reset_expire_minutes = password_reset_expire_minutes
        self._password_reset_frontend_url = password_reset_frontend_url
        self._oauth_google_client_id = oauth_google_client_id.strip()
        self._oauth_google_client_secret = oauth_google_client_secret.strip()
        self._oauth_github_client_id = oauth_github_client_id.strip()
        self._oauth_github_client_secret = oauth_github_client_secret.strip()
        self._oauth_allowed_redirect_base = oauth_allowed_redirect_base.strip().rstrip("/")
        self._oauth_states: dict[str, tuple[str, str, datetime]] = {}

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

        return self._create_token(normalized_username, role="user")

    def login(self, username: str, password: str) -> AuthTokenResult:
        normalized_username = username.strip()
        user = self._user_repository.get_by_username(normalized_username)
        if user is None:
            raise InvalidCredentialsError("Invalid username or password")

        if not user.is_active:
            raise InvalidCredentialsError("Account is disabled")

        if not self._verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid username or password")

        return self._create_token(user.username, role=user.role)

    def forgot_password(self, username: str, redirect_uri: str) -> ForgotPasswordResult:
        generic_message = "Nếu tài khoản tồn tại, bạn sẽ nhận được liên kết đặt lại mật khẩu."
        normalized_username = username.strip()
        if not normalized_username:
            return ForgotPasswordResult(message=generic_message)

        user = self._user_repository.get_by_username(normalized_username)
        if user is None:
            return ForgotPasswordResult(message=generic_message)

        token = self._create_password_reset_token(user.username)
        reset_base = self._resolve_reset_redirect_uri(redirect_uri)
        separator = "&" if "?" in reset_base else "?"
        reset_url = f"{reset_base}{separator}{urlencode({'reset_token': token})}"

        return ForgotPasswordResult(
            message=generic_message,
            reset_token=token,
            reset_url=reset_url,
        )

    def reset_password(self, token: str, new_password: str) -> None:
        username = self._decode_password_reset_token(token)
        password_hash = self._hash_password(new_password)
        updated = self._user_repository.update_password_hash(username, password_hash)
        if not updated:
            raise InvalidPasswordResetTokenError("Invalid or expired reset token")

    def build_oauth_start_url(self, provider: str, redirect_uri: str) -> OAuthStartResult:
        provider_normalized = self._normalize_provider(provider)
        redirect_uri_resolved = self._resolve_oauth_redirect_uri(redirect_uri)

        state = secrets.token_urlsafe(24)
        expires_at = datetime.now(UTC) + timedelta(minutes=OAUTH_STATE_EXPIRE_MINUTES)
        self._oauth_states[state] = (provider_normalized, redirect_uri_resolved, expires_at)
        self._cleanup_oauth_state_store()

        if provider_normalized == "google":
            self._ensure_oauth_configured("google")
            query = urlencode(
                {
                    "client_id": self._oauth_google_client_id,
                    "redirect_uri": redirect_uri_resolved,
                    "response_type": "code",
                    "scope": "openid email profile",
                    "state": state,
                    "access_type": "online",
                    "prompt": "consent",
                }
            )
            return OAuthStartResult(authorization_url=f"{GOOGLE_AUTH_URL}?{query}", state=state)

        if provider_normalized == "github":
            self._ensure_oauth_configured("github")
            query = urlencode(
                {
                    "client_id": self._oauth_github_client_id,
                    "redirect_uri": redirect_uri_resolved,
                    "scope": "read:user user:email",
                    "state": state,
                }
            )
            return OAuthStartResult(authorization_url=f"{GITHUB_AUTH_URL}?{query}", state=state)

        raise OAuthProviderNotSupportedError("Provider is not supported")

    def complete_oauth_login(
        self,
        provider: str,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> tuple[str, AuthTokenResult]:
        provider_normalized = self._normalize_provider(provider)
        redirect_uri_resolved = self._resolve_oauth_redirect_uri(redirect_uri)
        self._validate_oauth_state(state, provider_normalized, redirect_uri_resolved)

        oauth_email = self._exchange_oauth_code_for_email(
            provider=provider_normalized,
            code=code,
            redirect_uri=redirect_uri_resolved,
        )

        if not oauth_email:
            raise InvalidCredentialsError("Không thể lấy email từ nhà cung cấp OAuth")

        username = oauth_email.strip().lower()
        user = self._user_repository.get_by_username(username)
        user_role = "user"
        if user is None:
            if not self._registration_enabled:
                raise RegistrationDisabledError("Registration is disabled")

            password_hash = self._hash_password(secrets.token_urlsafe(48))
            self._user_repository.add(UserAccount(username=username, password_hash=password_hash))
        else:
            user_role = user.role

        token = self._create_token(username, role=user_role)
        return username, token

    def _create_token(self, username: str, role: str = "user") -> AuthTokenResult:
        normalized_role = "admin" if str(role).strip().lower() == "admin" else "user"
        expires_delta = timedelta(minutes=self._token_expire_minutes)
        expiration = datetime.now(UTC) + expires_delta
        payload = {
            "sub": username,
            "exp": expiration,
            "role": normalized_role,
        }
        token = jwt.encode(payload, self._secret_key, algorithm=JWT_ALGORITHM)

        return AuthTokenResult(
            access_token=token,
            token_type="bearer",
            expires_in=int(expires_delta.total_seconds()),
            username=username,
            role=normalized_role,
        )

    def _create_password_reset_token(self, username: str) -> str:
        expiration = datetime.now(UTC) + timedelta(minutes=self._password_reset_expire_minutes)
        payload = {
            "sub": username,
            "exp": expiration,
            "purpose": "password_reset",
        }
        return jwt.encode(payload, self._secret_key, algorithm=JWT_ALGORITHM)

    def _decode_password_reset_token(self, token: str) -> str:
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[JWT_ALGORITHM])
        except Exception as exc:
            raise InvalidPasswordResetTokenError("Invalid or expired reset token") from exc

        if payload.get("purpose") != "password_reset":
            raise InvalidPasswordResetTokenError("Invalid or expired reset token")

        username = str(payload.get("sub", "")).strip()
        if not username:
            raise InvalidPasswordResetTokenError("Invalid or expired reset token")
        return username

    def _resolve_reset_redirect_uri(self, requested_redirect_uri: str) -> str:
        candidate = (requested_redirect_uri or "").strip()
        if candidate and self._is_redirect_allowed(candidate):
            return candidate
        return self._password_reset_frontend_url

    def _resolve_oauth_redirect_uri(self, requested_redirect_uri: str) -> str:
        candidate = (requested_redirect_uri or "").strip()
        if not candidate:
            candidate = self._password_reset_frontend_url
        if not self._is_redirect_allowed(candidate):
            raise OAuthStateInvalidError("Redirect URI is not allowed")
        return candidate

    def _is_redirect_allowed(self, redirect_uri: str) -> bool:
        if not self._oauth_allowed_redirect_base:
            return True
        base = self._oauth_allowed_redirect_base
        return redirect_uri.startswith(base)

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        normalized = provider.strip().lower()
        if normalized not in {"google", "github"}:
            raise OAuthProviderNotSupportedError("Provider is not supported")
        return normalized

    def _ensure_oauth_configured(self, provider: str) -> None:
        if provider == "google":
            if not self._oauth_google_client_id or not self._oauth_google_client_secret:
                raise OAuthConfigurationError("Google OAuth is not configured")
            return

        if provider == "github":
            if not self._oauth_github_client_id or not self._oauth_github_client_secret:
                raise OAuthConfigurationError("GitHub OAuth is not configured")
            return

        raise OAuthProviderNotSupportedError("Provider is not supported")

    def _validate_oauth_state(self, state: str, provider: str, redirect_uri: str) -> None:
        raw_state = state.strip()
        item = self._oauth_states.pop(raw_state, None)
        if item is None:
            raise OAuthStateInvalidError("OAuth state is invalid or expired")

        expected_provider, expected_redirect, expires_at = item
        if datetime.now(UTC) > expires_at:
            raise OAuthStateInvalidError("OAuth state is invalid or expired")
        if expected_provider != provider:
            raise OAuthStateInvalidError("OAuth state is invalid or expired")
        if expected_redirect != redirect_uri:
            raise OAuthStateInvalidError("OAuth state is invalid or expired")

    def _cleanup_oauth_state_store(self) -> None:
        now = datetime.now(UTC)
        expired_keys = [key for key, (_, _, exp) in self._oauth_states.items() if now > exp]
        for key in expired_keys:
            self._oauth_states.pop(key, None)

    def _exchange_oauth_code_for_email(self, provider: str, code: str, redirect_uri: str) -> str:
        if provider == "google":
            return self._exchange_google_code_for_email(code=code, redirect_uri=redirect_uri)
        if provider == "github":
            return self._exchange_github_code_for_email(code=code, redirect_uri=redirect_uri)
        raise OAuthProviderNotSupportedError("Provider is not supported")

    def _exchange_google_code_for_email(self, code: str, redirect_uri: str) -> str:
        self._ensure_oauth_configured("google")
        with httpx.Client(timeout=20.0) as client:
            token_resp = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._oauth_google_client_id,
                    "client_secret": self._oauth_google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            token_resp.raise_for_status()
            access_token = token_resp.json().get("access_token", "")
            if not access_token:
                raise InvalidCredentialsError("Google OAuth failed")

            info_resp = client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            info_resp.raise_for_status()
            payload = info_resp.json()

        email = str(payload.get("email", "")).strip().lower()
        if not email:
            raise InvalidCredentialsError("Google account does not expose email")
        return email

    def _exchange_github_code_for_email(self, code: str, redirect_uri: str) -> str:
        self._ensure_oauth_configured("github")
        headers = {
            "Accept": "application/json",
            "User-Agent": "AIChatBox",
        }
        with httpx.Client(timeout=20.0, headers=headers) as client:
            token_resp = client.post(
                GITHUB_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._oauth_github_client_id,
                    "client_secret": self._oauth_github_client_secret,
                    "redirect_uri": redirect_uri,
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json().get("access_token", "")
            if not access_token:
                raise InvalidCredentialsError("GitHub OAuth failed")

            user_resp = client.get(
                GITHUB_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_resp.raise_for_status()
            user_payload = user_resp.json()

            email = str(user_payload.get("email", "")).strip().lower()
            if email:
                return email

            emails_resp = client.get(
                GITHUB_EMAILS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            emails_resp.raise_for_status()
            emails_payload = emails_resp.json()

        for row in emails_payload:
            if row.get("primary") and row.get("verified") and row.get("email"):
                return str(row.get("email")).strip().lower()

        for row in emails_payload:
            if row.get("verified") and row.get("email"):
                return str(row.get("email")).strip().lower()

        user_id = str(user_payload.get("id", "")).strip()
        if user_id:
            return f"github_{user_id}"

        raise InvalidCredentialsError("GitHub account does not expose email")

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
