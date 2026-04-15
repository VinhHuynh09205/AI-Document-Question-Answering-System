import sqlite3
from pathlib import Path

from app.models.entities import UserAccount
from app.repositories.interfaces.user_repository import IUserRepository


class SqliteUserRepository(IUserRepository):
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def get_by_username(self, username: str) -> UserAccount | None:
        normalized = username.strip().lower()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT username, password_hash FROM users WHERE lower(username) = ?",
                (normalized,),
            ).fetchone()

        if row is None:
            return None

        return UserAccount(username=row[0], password_hash=row[1])

    def add(self, user: UserAccount) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (user.username, user.password_hash),
            )
            conn.commit()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)
