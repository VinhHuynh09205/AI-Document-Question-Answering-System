from app.models.entities import UserAccount
from app.repositories.interfaces.user_repository import IUserRepository
from app.repositories.mysql_utils import MySqlConfig, connect, ensure_database


class MySqlUserRepository(IUserRepository):
    def __init__(self, config: MySqlConfig) -> None:
        self._config = config
        ensure_database(config)
        self._initialize()

    def get_by_username(self, username: str) -> UserAccount | None:
        normalized = username.strip().lower()
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT username, password_hash FROM users WHERE lower(username) = %s",
                    (normalized,),
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return UserAccount(username=row[0], password_hash=row[1])

    def add(self, user: UserAccount) -> None:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                    (user.username, user.password_hash),
                )
            conn.commit()

    def _initialize(self) -> None:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        username VARCHAR(64) PRIMARY KEY,
                        password_hash VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            conn.commit()
