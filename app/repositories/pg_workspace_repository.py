import uuid
from datetime import UTC, datetime

from app.models.entities import ChatMessage, ChatSession, StoredDocument
from app.repositories.interfaces.workspace_repository import IWorkspaceRepository
from app.repositories.pg_utils import PgConfig, connect, ensure_database


_DOCUMENT_SELECT_COLUMNS = (
    "document_id, chat_id, username, original_name, stored_path, created_at, "
    "file_hash, file_size, version, updated_at"
)


class PgWorkspaceRepository(IWorkspaceRepository):
    def __init__(self, config: PgConfig) -> None:
        self._config = config
        ensure_database(config)
        self._initialize()

    def create_chat(self, username: str, title: str) -> ChatSession:
        chat_id = uuid.uuid4().hex
        created_at = self._now_iso()
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chats (chat_id, username, title, created_at) VALUES (%s, %s, %s, %s)",
                    (chat_id, username, title, created_at),
                )
            conn.commit()
        finally:
            conn.close()
        return ChatSession(chat_id=chat_id, username=username, title=title, created_at=created_at)

    def get_chat(self, username: str, chat_id: str) -> ChatSession | None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT chat_id, username, title, created_at FROM chats WHERE username = %s AND chat_id = %s",
                    (username, chat_id),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return ChatSession(chat_id=row[0], username=row[1], title=row[2], created_at=self._to_iso(row[3]))

    def list_chats(self, username: str) -> list[ChatSession]:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT chat_id, username, title, created_at FROM chats WHERE username = %s ORDER BY created_at DESC",
                    (username,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        return [
            ChatSession(chat_id=row[0], username=row[1], title=row[2], created_at=self._to_iso(row[3]))
            for row in rows
        ]

    def add_document(
        self,
        username: str,
        chat_id: str,
        original_name: str,
        stored_path: str,
        *,
        file_hash: str | None = None,
        file_size: int | None = None,
        version: int | None = None,
    ) -> StoredDocument:
        document_id = uuid.uuid4().hex
        created_at = self._now_iso()
        normalized_hash = str(file_hash or "").strip().lower() or None
        normalized_size = max(0, int(file_size or 0))

        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                resolved_version = int(version or 1)
                if normalized_hash and version is None:
                    cur.execute(
                        """
                        SELECT version
                        FROM documents
                        WHERE username = %s AND chat_id = %s AND file_hash = %s
                        ORDER BY version DESC
                        LIMIT 1
                        FOR UPDATE
                        """,
                        (username, chat_id, normalized_hash),
                    )
                    latest_row = cur.fetchone()
                    resolved_version = int(latest_row[0]) + 1 if latest_row else 1

                cur.execute(
                    """
                    INSERT INTO documents (
                        document_id,
                        chat_id,
                        username,
                        original_name,
                        stored_path,
                        created_at,
                        file_hash,
                        file_size,
                        version,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING document_id, chat_id, username, original_name, stored_path, created_at,
                              file_hash, file_size, version, updated_at
                    """,
                    (
                        document_id,
                        chat_id,
                        username,
                        original_name,
                        stored_path,
                        created_at,
                        normalized_hash,
                        normalized_size,
                        max(1, resolved_version),
                        created_at,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if row is None:
            raise RuntimeError("Failed to persist document metadata")
        return self._row_to_document(row)

    def get_document(self, username: str, document_id: str) -> StoredDocument | None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_DOCUMENT_SELECT_COLUMNS} FROM documents WHERE username = %s AND document_id = %s",
                    (username, document_id),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return self._row_to_document(row)

    def find_document_by_hash(self, username: str, chat_id: str, file_hash: str) -> StoredDocument | None:
        normalized_hash = str(file_hash or "").strip().lower()
        if not normalized_hash:
            return None

        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {_DOCUMENT_SELECT_COLUMNS}
                    FROM documents
                    WHERE username = %s AND chat_id = %s AND file_hash = %s
                    ORDER BY version DESC, created_at DESC
                    LIMIT 1
                    """,
                    (username, chat_id, normalized_hash),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return self._row_to_document(row)

    def list_documents(self, username: str, chat_id: str) -> list[StoredDocument]:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {_DOCUMENT_SELECT_COLUMNS}
                    FROM documents
                    WHERE username = %s AND chat_id = %s
                    ORDER BY created_at ASC, document_id ASC
                    """,
                    (username, chat_id),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        return [self._row_to_document(row) for row in rows]

    def add_message(self, username: str, chat_id: str, role: str, content: str) -> ChatMessage:
        message_id = uuid.uuid4().hex
        created_at = self._now_iso()
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO messages (message_id, chat_id, username, role, content, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (message_id, chat_id, username, role, content, created_at))
            conn.commit()
        finally:
            conn.close()
        return ChatMessage(message_id=message_id, chat_id=chat_id, username=username,
                          role=role, content=content, created_at=created_at)

    def list_messages(self, username: str, chat_id: str, limit: int = 200) -> list[ChatMessage]:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id, chat_id, username, role, content, created_at
                    FROM messages WHERE username = %s AND chat_id = %s
                    ORDER BY created_at ASC LIMIT %s
                """, (username, chat_id, limit))
                rows = cur.fetchall()
        finally:
            conn.close()
        return [
            ChatMessage(message_id=row[0], chat_id=row[1], username=row[2],
                        role=row[3], content=row[4], created_at=self._to_iso(row[5]))
            for row in rows
        ]

    def rename_chat(self, username: str, chat_id: str, new_title: str) -> ChatSession | None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE chats SET title = %s WHERE username = %s AND chat_id = %s",
                    (new_title, username, chat_id),
                )
                if cur.rowcount == 0:
                    return None
            conn.commit()
        finally:
            conn.close()
        return self.get_chat(username, chat_id)

    def delete_chat(self, username: str, chat_id: str) -> bool:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM messages WHERE username = %s AND chat_id = %s", (username, chat_id))
                cur.execute("DELETE FROM documents WHERE username = %s AND chat_id = %s", (username, chat_id))
                cur.execute("DELETE FROM chats WHERE username = %s AND chat_id = %s", (username, chat_id))
                deleted = cur.rowcount > 0
            conn.commit()
        finally:
            conn.close()
        return deleted

    def delete_documents_for_chat(self, username: str, chat_id: str) -> int:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM documents WHERE username = %s AND chat_id = %s",
                    (username, chat_id),
                )
                deleted_count = cur.rowcount
            conn.commit()
        finally:
            conn.close()
        return max(0, int(deleted_count))

    def delete_messages_for_chat(self, username: str, chat_id: str) -> int:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM messages WHERE username = %s AND chat_id = %s",
                    (username, chat_id),
                )
                deleted_count = cur.rowcount
            conn.commit()
        finally:
            conn.close()
        return max(0, int(deleted_count))

    def rename_document(self, username: str, document_id: str, new_name: str) -> StoredDocument | None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE documents
                    SET original_name = %s, updated_at = %s
                    WHERE username = %s AND document_id = %s
                    """,
                    (new_name, self._now_iso(), username, document_id),
                )
                if cur.rowcount == 0:
                    return None
                cur.execute(
                    f"SELECT {_DOCUMENT_SELECT_COLUMNS} FROM documents WHERE document_id = %s",
                    (document_id,),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()
        if row is None:
            return None
        return self._row_to_document(row)

    def delete_document(self, username: str, document_id: str) -> bool:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM documents WHERE username = %s AND document_id = %s",
                    (username, document_id),
                )
                deleted = cur.rowcount > 0
            conn.commit()
        finally:
            conn.close()
        return deleted

    def _initialize(self) -> None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chats (
                        chat_id VARCHAR(64) PRIMARY KEY,
                        username VARCHAR(64) NOT NULL,
                        title VARCHAR(200) NOT NULL,
                        created_at VARCHAR(64) NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id VARCHAR(64) PRIMARY KEY,
                        chat_id VARCHAR(64) NOT NULL,
                        username VARCHAR(64) NOT NULL,
                        original_name VARCHAR(255) NOT NULL,
                        stored_path TEXT NOT NULL,
                        created_at VARCHAR(64) NOT NULL,
                        file_hash VARCHAR(128) NULL,
                        file_size BIGINT NOT NULL DEFAULT 0,
                        version INTEGER NOT NULL DEFAULT 1,
                        updated_at VARCHAR(64) NOT NULL DEFAULT ''
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        message_id VARCHAR(64) PRIMARY KEY,
                        chat_id VARCHAR(64) NOT NULL,
                        username VARCHAR(64) NOT NULL,
                        role VARCHAR(16) NOT NULL,
                        content TEXT NOT NULL,
                        created_at VARCHAR(64) NOT NULL
                    )
                """)

                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'documents'
                    """
                )
                document_columns = {row[0] for row in cur.fetchall()}

                if "file_hash" not in document_columns:
                    cur.execute("ALTER TABLE documents ADD COLUMN file_hash VARCHAR(128) NULL")
                if "file_size" not in document_columns:
                    cur.execute("ALTER TABLE documents ADD COLUMN file_size BIGINT NOT NULL DEFAULT 0")
                if "version" not in document_columns:
                    cur.execute("ALTER TABLE documents ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
                if "updated_at" not in document_columns:
                    cur.execute("ALTER TABLE documents ADD COLUMN updated_at VARCHAR(64) NOT NULL DEFAULT ''")

                cur.execute(
                    """
                    UPDATE documents
                    SET updated_at = created_at
                    WHERE updated_at IS NULL OR updated_at = ''
                    """
                )

                cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_chat ON documents (chat_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_chat ON documents (username, chat_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_chat_hash ON documents (username, chat_id, file_hash)")
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_user_chat_hash_version_unique
                    ON documents (username, chat_id, file_hash, version)
                    WHERE file_hash IS NOT NULL
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages (chat_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_chat ON messages (username, chat_id)")
            conn.commit()
        finally:
            conn.close()

    def _row_to_document(self, row) -> StoredDocument:
        created_at = self._to_iso(row[5])
        updated_at = self._to_iso(row[9]) if row[9] else created_at
        return StoredDocument(
            document_id=str(row[0]),
            chat_id=str(row[1]),
            username=str(row[2]),
            original_name=str(row[3]),
            stored_path=str(row[4]),
            created_at=created_at,
            file_hash=str(row[6] or ""),
            file_size=max(0, int(row[7] or 0)),
            version=max(1, int(row[8] or 1)),
            updated_at=updated_at,
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _to_iso(value) -> str:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
