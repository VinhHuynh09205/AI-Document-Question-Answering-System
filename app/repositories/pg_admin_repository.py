from app.models.entities import AuditLogEntry
from app.repositories.interfaces.admin_repository import IAdminRepository
from app.repositories.pg_utils import PgConfig, connect, ensure_database


class PgAdminRepository(IAdminRepository):
    def __init__(self, config: PgConfig) -> None:
        self._config = config
        ensure_database(config)
        self._initialize()

    def get_stats(self) -> dict:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                users = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM chats")
                chats = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM documents")
                documents = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM messages")
                messages = cur.fetchone()[0]
        finally:
            conn.close()
        return {
            "total_users": users, "total_chats": chats,
            "total_documents": documents, "total_messages": messages,
        }

    def count_users(self) -> int:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                return cur.fetchone()[0]
        finally:
            conn.close()

    def count_chats(self) -> int:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM chats")
                return cur.fetchone()[0]
        finally:
            conn.close()

    def count_documents(self) -> int:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM documents")
                return cur.fetchone()[0]
        finally:
            conn.close()

    def count_messages(self) -> int:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM messages")
                return cur.fetchone()[0]
        finally:
            conn.close()

    def count_recent_users(self, days: int = 7) -> int:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM users WHERE created_at >= NOW() - make_interval(days => %s)",
                    (days,),
                )
                return cur.fetchone()[0]
        finally:
            conn.close()

    def top_users_by_messages(self, limit: int = 10) -> list[dict]:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT username, COUNT(*) as msg_count
                    FROM messages WHERE role = 'user'
                    GROUP BY username ORDER BY msg_count DESC LIMIT %s
                """, (limit,))
                rows = cur.fetchall()
        finally:
            conn.close()
        return [{"username": row[0], "message_count": row[1]} for row in rows]

    def messages_per_day(self, days: int = 30) -> list[dict]:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    WITH normalized_messages AS (
                        SELECT
                            CASE
                                WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}'
                                    THEN created_at::timestamptz
                                ELSE NULL
                            END AS created_ts
                        FROM messages
                    )
                    SELECT DATE(created_ts) as day, COUNT(*) as count
                    FROM normalized_messages
                    WHERE created_ts IS NOT NULL
                      AND created_ts >= NOW() - make_interval(days => %s)
                    GROUP BY DATE(created_ts)
                    ORDER BY day ASC
                """, (days,))
                rows = cur.fetchall()
        finally:
            conn.close()
        return [{"date": str(row[0]), "count": row[1]} for row in rows]

    def add_audit_log(self, entry: AuditLogEntry) -> None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO admin_audit_log (
                        log_id, admin_username, action, target, detail, created_at,
                        ip_address, user_agent, request_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    entry.log_id,
                    entry.admin_username,
                    entry.action,
                    entry.target,
                    entry.detail,
                    entry.created_at,
                    entry.ip_address,
                    entry.user_agent,
                    entry.request_id,
                ))
            conn.commit()
        finally:
            conn.close()

    def list_audit_logs(self, offset: int = 0, limit: int = 50) -> list[AuditLogEntry]:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT log_id, admin_username, action, target, detail, created_at,
                           ip_address, user_agent, request_id
                    FROM admin_audit_log ORDER BY created_at DESC LIMIT %s OFFSET %s
                """, (limit, offset))
                rows = cur.fetchall()
        finally:
            conn.close()
        return [
            AuditLogEntry(log_id=row[0], admin_username=row[1], action=row[2],
                          target=row[3], detail=row[4], created_at=str(row[5]),
                          ip_address=str(row[6] or ""), user_agent=str(row[7] or ""),
                          request_id=str(row[8] or ""))
            for row in rows
        ]

    def count_audit_logs(self) -> int:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM admin_audit_log")
                return cur.fetchone()[0]
        finally:
            conn.close()

    def _initialize(self) -> None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS admin_audit_log (
                        log_id VARCHAR(64) PRIMARY KEY,
                        admin_username VARCHAR(64) NOT NULL,
                        action VARCHAR(64) NOT NULL,
                        target VARCHAR(255) NOT NULL DEFAULT '',
                        detail TEXT NOT NULL,
                        created_at VARCHAR(64) NOT NULL,
                        ip_address VARCHAR(64) NOT NULL DEFAULT '',
                        user_agent TEXT NOT NULL DEFAULT '',
                        request_id VARCHAR(128) NOT NULL DEFAULT ''
                    )
                """)
                cur.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'admin_audit_log'
                """)
                columns = {row[0] for row in cur.fetchall()}
                if "ip_address" not in columns:
                    cur.execute("ALTER TABLE admin_audit_log ADD COLUMN ip_address VARCHAR(64) NOT NULL DEFAULT ''")
                if "user_agent" not in columns:
                    cur.execute("ALTER TABLE admin_audit_log ADD COLUMN user_agent TEXT NOT NULL DEFAULT ''")
                if "request_id" not in columns:
                    cur.execute("ALTER TABLE admin_audit_log ADD COLUMN request_id VARCHAR(128) NOT NULL DEFAULT ''")
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_audit_created ON admin_audit_log (created_at)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_audit_admin ON admin_audit_log (admin_username)
                """)
            conn.commit()
        finally:
            conn.close()
