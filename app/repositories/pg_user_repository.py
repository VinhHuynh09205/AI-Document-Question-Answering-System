from app.models.entities import UserAccount
from app.repositories.interfaces.user_repository import IUserRepository
from app.repositories.pg_utils import PgConfig, connect, ensure_database


class PgUserRepository(IUserRepository):
    def __init__(self, config: PgConfig) -> None:
        self._config = config
        ensure_database(config)
        self._initialize()

    def get_by_username(self, username: str) -> UserAccount | None:
        normalized = username.strip().lower()
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT username, password_hash, role, is_active, created_at FROM users WHERE lower(username) = %s",
                    (normalized,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return UserAccount(
            username=row[0], password_hash=row[1], role=row[2] or "user",
            is_active=bool(row[3]), created_at=str(row[4]) if row[4] else "",
        )

    def add(self, user: UserAccount) -> None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, is_active) VALUES (%s, %s, %s, %s)",
                    (user.username, user.password_hash, user.role, user.is_active),
                )
            conn.commit()
        finally:
            conn.close()

    def update_password_hash(self, username: str, password_hash: str) -> bool:
        normalized = username.strip().lower()
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE lower(username) = %s",
                    (password_hash, normalized),
                )
                affected = cur.rowcount
            conn.commit()
            return affected > 0
        finally:
            conn.close()

    def list_all(self, offset: int = 0, limit: int = 50) -> list[UserAccount]:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT username, password_hash, role, is_active, created_at FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (limit, offset),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        return [
            UserAccount(username=row[0], password_hash=row[1], role=row[2] or "user",
                        is_active=bool(row[3]), created_at=str(row[4]) if row[4] else "")
            for row in rows
        ]

    def count_all(self) -> int:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                row = cur.fetchone()
        finally:
            conn.close()
        return row[0] if row else 0

    def update_role(self, username: str, role: str) -> bool:
        normalized = username.strip().lower()
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET role = %s WHERE lower(username) = %s",
                    (role, normalized),
                )
                affected = cur.rowcount
            conn.commit()
            return affected > 0
        finally:
            conn.close()

    def update_active(self, username: str, is_active: bool) -> bool:
        normalized = username.strip().lower()
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET is_active = %s WHERE lower(username) = %s",
                    (is_active, normalized),
                )
                affected = cur.rowcount
            conn.commit()
            return affected > 0
        finally:
            conn.close()

    def delete(self, username: str) -> bool:
        normalized = username.strip().lower()
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM users WHERE lower(username) = %s",
                    (normalized,),
                )
                affected = cur.rowcount
            conn.commit()
            return affected > 0
        finally:
            conn.close()

    def _initialize(self) -> None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        username VARCHAR(64) PRIMARY KEY,
                        password_hash VARCHAR(255) NOT NULL,
                        role VARCHAR(16) NOT NULL DEFAULT 'user',
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Migration: add columns if missing
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'users' AND table_schema = 'public'
                """)
                columns = {row[0] for row in cur.fetchall()}
                if "role" not in columns:
                    cur.execute("ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user'")
                if "is_active" not in columns:
                    cur.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE")
            conn.commit()
        finally:
            conn.close()
