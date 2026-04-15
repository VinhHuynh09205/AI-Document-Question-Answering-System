import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.models.entities import ChatMessage, ChatSession, StoredDocument
from app.repositories.interfaces.workspace_repository import IWorkspaceRepository


class SqliteWorkspaceRepository(IWorkspaceRepository):
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_chat(self, username: str, title: str) -> ChatSession:
        chat_id = uuid.uuid4().hex
        created_at = self._now_iso()

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chats (chat_id, username, title, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, username, title, created_at),
            )
            conn.commit()

        return ChatSession(chat_id=chat_id, username=username, title=title, created_at=created_at)

    def get_chat(self, username: str, chat_id: str) -> ChatSession | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT chat_id, username, title, created_at FROM chats WHERE username = ? AND chat_id = ?",
                (username, chat_id),
            ).fetchone()

        if row is None:
            return None

        return ChatSession(chat_id=row[0], username=row[1], title=row[2], created_at=row[3])

    def list_chats(self, username: str) -> list[ChatSession]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chat_id, username, title, created_at FROM chats WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()

        return [
            ChatSession(chat_id=row[0], username=row[1], title=row[2], created_at=row[3])
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

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (document_id, chat_id, username, original_name, stored_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
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
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT document_id, chat_id, username, original_name, stored_path, created_at
                FROM documents
                WHERE username = ? AND chat_id = ?
                ORDER BY created_at ASC
                """,
                (username, chat_id),
            ).fetchall()

        return [
            StoredDocument(
                document_id=row[0],
                chat_id=row[1],
                username=row[2],
                original_name=row[3],
                stored_path=row[4],
                created_at=row[5],
            )
            for row in rows
        ]

    def add_message(self, username: str, chat_id: str, role: str, content: str) -> ChatMessage:
        message_id = uuid.uuid4().hex
        created_at = self._now_iso()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (message_id, chat_id, username, role, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
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
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT message_id, chat_id, username, role, content, created_at
                FROM messages
                WHERE username = ? AND chat_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (username, chat_id, limit),
            ).fetchall()

        return [
            ChatMessage(
                message_id=row[0],
                chat_id=row[1],
                username=row[2],
                role=row[3],
                content=row[4],
                created_at=row[5],
            )
            for row in rows
        ]

    def rename_chat(self, username: str, chat_id: str, new_title: str) -> ChatSession | None:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE chats SET title = ? WHERE username = ? AND chat_id = ?",
                (new_title, username, chat_id),
            )
            if cursor.rowcount == 0:
                return None
            conn.commit()
        return self.get_chat(username, chat_id)

    def delete_chat(self, username: str, chat_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE username = ? AND chat_id = ?", (username, chat_id))
            conn.execute("DELETE FROM documents WHERE username = ? AND chat_id = ?", (username, chat_id))
            cursor = conn.execute("DELETE FROM chats WHERE username = ? AND chat_id = ?", (username, chat_id))
            deleted = cursor.rowcount > 0
            conn.commit()
        return deleted

    def rename_document(self, username: str, document_id: str, new_name: str) -> StoredDocument | None:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE documents SET original_name = ? WHERE username = ? AND document_id = ?",
                (new_name, username, document_id),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT document_id, chat_id, username, original_name, stored_path, created_at FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return StoredDocument(
            document_id=row[0], chat_id=row[1], username=row[2],
            original_name=row[3], stored_path=row[4], created_at=row[5],
        )

    def delete_document(self, username: str, document_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM documents WHERE username = ? AND document_id = ?",
                (username, document_id),
            )
            deleted = cursor.rowcount > 0
            conn.commit()
        return deleted

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()
