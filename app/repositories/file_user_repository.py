import json
from pathlib import Path
from threading import RLock

from app.models.entities import UserAccount
from app.repositories.interfaces.user_repository import IUserRepository


class FileUserRepository(IUserRepository):
    def __init__(self, users_file_path: Path) -> None:
        self._users_file_path = users_file_path
        self._lock = RLock()
        self._ensure_file_exists()

    def get_by_username(self, username: str) -> UserAccount | None:
        normalized = username.strip().lower()
        users = self._read_all()
        for row in users:
            if row.get("username", "").lower() == normalized:
                return UserAccount(
                    username=row["username"],
                    password_hash=row["password_hash"],
                    role=row.get("role", "user"),
                    is_active=row.get("is_active", True),
                    created_at=row.get("created_at", ""),
                )
        return None

    def add(self, user: UserAccount) -> None:
        with self._lock:
            users = self._read_all()
            exists = any(
                row.get("username", "").lower() == user.username.lower()
                for row in users
            )
            if exists:
                raise ValueError("User already exists")

            users.append(
                {
                    "username": user.username,
                    "password_hash": user.password_hash,
                    "role": user.role,
                    "is_active": user.is_active,
                }
            )
            self._write_all(users)

    def update_password_hash(self, username: str, password_hash: str) -> bool:
        normalized = username.strip().lower()
        with self._lock:
            users = self._read_all()
            updated = False
            for row in users:
                if row.get("username", "").lower() == normalized:
                    row["password_hash"] = password_hash
                    updated = True
                    break

            if updated:
                self._write_all(users)

            return updated

    def list_all(self, offset: int = 0, limit: int = 50) -> list[UserAccount]:
        users = self._read_all()
        sliced = users[offset: offset + limit]
        return [
            UserAccount(
                username=row["username"],
                password_hash=row["password_hash"],
                role=row.get("role", "user"),
                is_active=row.get("is_active", True),
                created_at=row.get("created_at", ""),
            )
            for row in sliced
        ]

    def count_all(self) -> int:
        return len(self._read_all())

    def update_role(self, username: str, role: str) -> bool:
        normalized = username.strip().lower()
        with self._lock:
            users = self._read_all()
            for row in users:
                if row.get("username", "").lower() == normalized:
                    row["role"] = role
                    self._write_all(users)
                    return True
        return False

    def update_active(self, username: str, is_active: bool) -> bool:
        normalized = username.strip().lower()
        with self._lock:
            users = self._read_all()
            for row in users:
                if row.get("username", "").lower() == normalized:
                    row["is_active"] = is_active
                    self._write_all(users)
                    return True
        return False

    def delete(self, username: str) -> bool:
        normalized = username.strip().lower()
        with self._lock:
            users = self._read_all()
            original_len = len(users)
            users = [row for row in users if row.get("username", "").lower() != normalized]
            if len(users) < original_len:
                self._write_all(users)
                return True
        return False

    def _ensure_file_exists(self) -> None:
        self._users_file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._users_file_path.exists():
            self._users_file_path.write_text("[]", encoding="utf-8")

    def _read_all(self) -> list[dict]:
        with self._lock:
            text = self._users_file_path.read_text(encoding="utf-8").strip()
            if not text:
                return []
            return json.loads(text)

    def _write_all(self, users: list[dict]) -> None:
        serialized = json.dumps(users, ensure_ascii=True, indent=2)
        self._users_file_path.write_text(serialized, encoding="utf-8")
