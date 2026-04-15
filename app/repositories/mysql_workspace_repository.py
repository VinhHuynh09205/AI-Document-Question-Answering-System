import uuid
from datetime import UTC, datetime

from app.models.entities import ChatMessage, ChatSession, StoredDocument
from app.repositories.interfaces.workspace_repository import IWorkspaceRepository
from app.repositories.mysql_utils import MySqlConfig, connect, ensure_database


class MySqlWorkspaceRepository(IWorkspaceRepository):
    def __init__(self, config: MySqlConfig) -> None:
        self._config = config
        ensure_database(config)
        self._initialize()

    def create_chat(self, username: str, title: str) -> ChatSession:
        chat_id = uuid.uuid4().hex
        created_at = self._now_iso()

        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO chats (chat_id, username, title, created_at) VALUES (%s, %s, %s, %s)",
                    (chat_id, username, title, created_at),
                )
            conn.commit()

        return ChatSession(chat_id=chat_id, username=username, title=title, created_at=created_at)

    def get_chat(self, username: str, chat_id: str) -> ChatSession | None:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT chat_id, username, title, created_at FROM chats WHERE username = %s AND chat_id = %s",
                    (username, chat_id),
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return ChatSession(
            chat_id=row[0],
            username=row[1],
            title=row[2],
            created_at=self._to_iso(row[3]),
        )

    def list_chats(self, username: str) -> list[ChatSession]:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT chat_id, username, title, created_at FROM chats WHERE username = %s ORDER BY created_at DESC",
                    (username,),
                )
                rows = cursor.fetchall()

        return [
            ChatSession(
                chat_id=row[0],
                username=row[1],
                title=row[2],
                created_at=self._to_iso(row[3]),
            )
            for row in rows
        ]

    def add_document(
        self,
        username: str,
        chat_id: str,
        original_name: str,
        stored_path: str,
    ) -> StoredDocument:
        document_id = uuid.uuid4().hex
        created_at = self._now_iso()

        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO documents (document_id, chat_id, username, original_name, stored_path, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (document_id, chat_id, username, original_name, stored_path, created_at),
                )
            conn.commit()

        return StoredDocument(
            document_id=document_id,
            chat_id=chat_id,
            username=username,
            original_name=original_name,
            stored_path=stored_path,
            created_at=created_at,
        )

    def list_documents(self, username: str, chat_id: str) -> list[StoredDocument]:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT document_id, chat_id, username, original_name, stored_path, created_at
                    FROM documents
                    WHERE username = %s AND chat_id = %s
                    ORDER BY created_at ASC
                    """,
                    (username, chat_id),
                )
                rows = cursor.fetchall()

        return [
            StoredDocument(
                document_id=row[0],
                chat_id=row[1],
                username=row[2],
                original_name=row[3],
                stored_path=row[4],
                created_at=self._to_iso(row[5]),
            )
            for row in rows
        ]

    def add_message(self, username: str, chat_id: str, role: str, content: str) -> ChatMessage:
        message_id = uuid.uuid4().hex
        created_at = self._now_iso()

        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO messages (message_id, chat_id, username, role, content, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (message_id, chat_id, username, role, content, created_at),
                )
            conn.commit()

        return ChatMessage(
            message_id=message_id,
            chat_id=chat_id,
            username=username,
            role=role,
            content=content,
            created_at=created_at,
        )

    def list_messages(self, username: str, chat_id: str, limit: int = 200) -> list[ChatMessage]:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT message_id, chat_id, username, role, content, created_at
                    FROM messages
                    WHERE username = %s AND chat_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (username, chat_id, limit),
                )
                rows = cursor.fetchall()

        return [
            ChatMessage(
                message_id=row[0],
                chat_id=row[1],
                username=row[2],
                role=row[3],
                content=row[4],
                created_at=self._to_iso(row[5]),
            )
            for row in rows
        ]

    def rename_chat(self, username: str, chat_id: str, new_title: str) -> ChatSession | None:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE chats SET title = %s WHERE username = %s AND chat_id = %s",
                    (new_title, username, chat_id),
                )
                if cursor.rowcount == 0:
                    return None
            conn.commit()
        return self.get_chat(username, chat_id)

    def delete_chat(self, username: str, chat_id: str) -> bool:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM messages WHERE username = %s AND chat_id = %s",
                    (username, chat_id),
                )
                cursor.execute(
                    "DELETE FROM documents WHERE username = %s AND chat_id = %s",
                    (username, chat_id),
                )
                cursor.execute(
                    "DELETE FROM chats WHERE username = %s AND chat_id = %s",
                    (username, chat_id),
                )
                deleted = cursor.rowcount > 0
            conn.commit()
        return deleted

    def rename_document(self, username: str, document_id: str, new_name: str) -> StoredDocument | None:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE documents SET original_name = %s WHERE username = %s AND document_id = %s",
                    (new_name, username, document_id),
                )
                if cursor.rowcount == 0:
                    return None
                cursor.execute(
                    "SELECT document_id, chat_id, username, original_name, stored_path, created_at FROM documents WHERE document_id = %s",
                    (document_id,),
                )
                row = cursor.fetchone()
            conn.commit()
        if row is None:
            return None
        return StoredDocument(
            document_id=row[0], chat_id=row[1], username=row[2],
            original_name=row[3], stored_path=row[4], created_at=self._to_iso(row[5]),
        )

    def delete_document(self, username: str, document_id: str) -> bool:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM documents WHERE username = %s AND document_id = %s",
                    (username, document_id),
                )
                deleted = cursor.rowcount > 0
            conn.commit()
        return deleted

    def _initialize(self) -> None:
        with connect(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chats (
                        chat_id VARCHAR(64) PRIMARY KEY,
                        username VARCHAR(64) NOT NULL,
                        title VARCHAR(200) NOT NULL,
                        created_at VARCHAR(64) NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id VARCHAR(64) PRIMARY KEY,
                        chat_id VARCHAR(64) NOT NULL,
                        username VARCHAR(64) NOT NULL,
                        original_name VARCHAR(255) NOT NULL,
                        stored_path TEXT NOT NULL,
                        created_at VARCHAR(64) NOT NULL,
                        INDEX idx_documents_chat (chat_id),
                        INDEX idx_documents_user_chat (username, chat_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        message_id VARCHAR(64) PRIMARY KEY,
                        chat_id VARCHAR(64) NOT NULL,
                        username VARCHAR(64) NOT NULL,
                        role VARCHAR(16) NOT NULL,
                        content LONGTEXT NOT NULL,
                        created_at VARCHAR(64) NOT NULL,
                        INDEX idx_messages_chat (chat_id),
                        INDEX idx_messages_user_chat (username, chat_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            conn.commit()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _to_iso(value) -> str:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
