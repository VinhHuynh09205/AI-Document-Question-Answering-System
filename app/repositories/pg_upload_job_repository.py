from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

from app.repositories.interfaces.upload_job_repository import IUploadJobRepository
from app.repositories.pg_utils import PgConfig, connect, ensure_database


_SELECT_COLUMNS = """
    job_id,
    username,
    chat_id,
    status,
    stage,
    progress,
    files_total,
    files_processed,
    chunks_total,
    chunks_indexed,
    original_names,
    file_paths,
    message,
    error,
    retry_count,
    max_retries,
    created_at,
    updated_at
"""


class PgUploadJobRepository(IUploadJobRepository):
    def __init__(self, config: PgConfig) -> None:
        self._config = config
        ensure_database(config)
        self._initialize()

    def create_job(
        self,
        *,
        username: str,
        chat_id: str,
        original_names: Sequence[str],
        file_paths: Sequence[str],
        max_retries: int,
        message: str | None = None,
    ) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        retries = max(0, int(max_retries))

        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO upload_jobs (
                        job_id,
                        username,
                        chat_id,
                        status,
                        stage,
                        progress,
                        files_total,
                        files_processed,
                        chunks_total,
                        chunks_indexed,
                        original_names,
                        file_paths,
                        message,
                        error,
                        retry_count,
                        max_retries,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s,
                        'queued',
                        'queued',
                        0,
                        %s,
                        0,
                        0,
                        0,
                        %s::jsonb,
                        %s::jsonb,
                        %s,
                        NULL,
                        0,
                        %s,
                        NOW(),
                        NOW()
                    )
                    RETURNING {_SELECT_COLUMNS}
                    """,
                    (
                        job_id,
                        username,
                        chat_id,
                        len(list(original_names)),
                        json.dumps(list(original_names), ensure_ascii=False),
                        json.dumps(list(file_paths), ensure_ascii=False),
                        message or "Đã nhận file, đang chờ xử lý",
                        retries,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        return self._row_to_snapshot(row)

    def get_job(self, *, job_id: str, username: str, chat_id: str) -> dict[str, Any] | None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {_SELECT_COLUMNS}
                    FROM upload_jobs
                    WHERE job_id = %s AND username = %s AND chat_id = %s
                    """,
                    (job_id, username, chat_id),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return self._row_to_snapshot(row)

    def get_job_by_id(self, *, job_id: str) -> dict[str, Any] | None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {_SELECT_COLUMNS}
                    FROM upload_jobs
                    WHERE job_id = %s
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return self._row_to_snapshot(row)

    def list_jobs(
        self,
        *,
        username: str,
        chat_id: str,
        limit: int = 20,
        include_terminal: bool = True,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))

        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                if include_terminal:
                    cur.execute(
                        f"""
                        SELECT {_SELECT_COLUMNS}
                        FROM upload_jobs
                        WHERE username = %s AND chat_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (username, chat_id, safe_limit),
                    )
                else:
                    cur.execute(
                        f"""
                        SELECT {_SELECT_COLUMNS}
                        FROM upload_jobs
                        WHERE username = %s AND chat_id = %s AND status IN ('queued', 'processing')
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (username, chat_id, safe_limit),
                    )
                rows = cur.fetchall()
        finally:
            conn.close()

        return [self._row_to_snapshot(row) for row in rows]

    def claim_next_queued_job(self) -> dict[str, Any] | None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    WITH candidate AS (
                        SELECT job_id AS candidate_job_id
                        FROM upload_jobs
                        WHERE status = 'queued'
                        ORDER BY created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE upload_jobs AS jobs
                    SET
                        status = 'processing',
                        stage = 'loading',
                        progress = 0,
                        files_processed = 0,
                        chunks_total = 0,
                        chunks_indexed = 0,
                        message = 'Đang xử lý tài liệu',
                        error = NULL,
                        updated_at = NOW()
                    FROM candidate
                    WHERE jobs.job_id = candidate.candidate_job_id
                    RETURNING { _SELECT_COLUMNS }
                    """,
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if row is None:
            return None
        return self._row_to_snapshot(row)

    def update_progress(
        self,
        *,
        job_id: str,
        stage: str | None = None,
        progress: int | None = None,
        files_processed: int | None = None,
        chunks_total: int | None = None,
        chunks_indexed: int | None = None,
        message: str | None = None,
    ) -> dict[str, Any] | None:
        safe_progress = None if progress is None else max(0, min(int(progress), 100))
        safe_files_processed = None if files_processed is None else max(0, int(files_processed))
        safe_chunks_total = None if chunks_total is None else max(0, int(chunks_total))
        safe_chunks_indexed = None if chunks_indexed is None else max(0, int(chunks_indexed))

        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE upload_jobs
                    SET
                        stage = COALESCE(%s, stage),
                        progress = COALESCE(%s, progress),
                        files_processed = COALESCE(%s, files_processed),
                        chunks_total = COALESCE(%s, chunks_total),
                        chunks_indexed = COALESCE(%s, chunks_indexed),
                        message = COALESCE(%s, message),
                        updated_at = NOW()
                    WHERE job_id = %s
                    RETURNING {_SELECT_COLUMNS}
                    """,
                    (
                        stage,
                        safe_progress,
                        safe_files_processed,
                        safe_chunks_total,
                        safe_chunks_indexed,
                        message,
                        job_id,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if row is None:
            return None
        return self._row_to_snapshot(row)

    def mark_completed(
        self,
        *,
        job_id: str,
        files_processed: int,
        chunks_indexed: int,
        message: str,
    ) -> dict[str, Any] | None:
        safe_files_processed = max(0, int(files_processed))
        safe_chunks_indexed = max(0, int(chunks_indexed))

        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE upload_jobs
                    SET
                        status = 'completed',
                        stage = 'completed',
                        progress = 100,
                        files_processed = GREATEST(files_processed, %s),
                        chunks_total = GREATEST(chunks_total, %s),
                        chunks_indexed = GREATEST(chunks_indexed, %s),
                        message = %s,
                        error = NULL,
                        updated_at = NOW()
                    WHERE job_id = %s
                    RETURNING {_SELECT_COLUMNS}
                    """,
                    (
                        safe_files_processed,
                        safe_chunks_indexed,
                        safe_chunks_indexed,
                        message,
                        job_id,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if row is None:
            return None
        return self._row_to_snapshot(row)

    def mark_failed(
        self,
        *,
        job_id: str,
        error: str,
        message: str | None = None,
    ) -> dict[str, Any] | None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE upload_jobs
                    SET
                        status = 'failed',
                        stage = 'failed',
                        progress = GREATEST(progress, 1),
                        message = COALESCE(%s, message),
                        error = %s,
                        updated_at = NOW()
                    WHERE job_id = %s
                    RETURNING {_SELECT_COLUMNS}
                    """,
                    (
                        message,
                        error,
                        job_id,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if row is None:
            return None
        return self._row_to_snapshot(row)

    def retry_job(self, *, job_id: str, username: str, chat_id: str) -> dict[str, Any] | None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE upload_jobs
                    SET
                        status = 'queued',
                        stage = 'queued',
                        progress = 0,
                        files_processed = 0,
                        chunks_total = 0,
                        chunks_indexed = 0,
                        message = 'Đã lên lịch thử lại',
                        error = NULL,
                        retry_count = retry_count + 1,
                        updated_at = NOW()
                    WHERE
                        job_id = %s
                        AND username = %s
                        AND chat_id = %s
                        AND status = 'failed'
                        AND retry_count < max_retries
                    RETURNING {_SELECT_COLUMNS}
                    """,
                    (job_id, username, chat_id),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if row is None:
            return None
        return self._row_to_snapshot(row)

    def requeue_stale_processing_jobs(self, *, stale_seconds: int) -> int:
        safe_stale_seconds = max(30, int(stale_seconds))

        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE upload_jobs
                    SET
                        status = 'queued',
                        stage = 'queued',
                        message = 'Khôi phục job sau khi tiến trình xử lý bị gián đoạn',
                        updated_at = NOW()
                    WHERE
                        status = 'processing'
                        AND updated_at < NOW() - (%s * INTERVAL '1 second')
                    """,
                    (safe_stale_seconds,),
                )
                affected = cur.rowcount
            conn.commit()
        finally:
            conn.close()

        return max(0, affected)

    def cleanup_expired_jobs(self, *, retention_seconds: int) -> int:
        safe_retention = max(300, int(retention_seconds))

        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM upload_jobs
                    WHERE
                        status IN ('completed', 'failed')
                        AND updated_at < NOW() - (%s * INTERVAL '1 second')
                    """,
                    (safe_retention,),
                )
                affected = cur.rowcount
            conn.commit()
        finally:
            conn.close()

        return max(0, affected)

    def _initialize(self) -> None:
        conn = connect(self._config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS upload_jobs (
                        job_id VARCHAR(64) PRIMARY KEY,
                        username VARCHAR(64) NOT NULL,
                        chat_id VARCHAR(64) NOT NULL,
                        status VARCHAR(16) NOT NULL,
                        stage VARCHAR(32) NOT NULL,
                        progress INTEGER NOT NULL DEFAULT 0,
                        files_total INTEGER NOT NULL DEFAULT 0,
                        files_processed INTEGER NOT NULL DEFAULT 0,
                        chunks_total INTEGER NOT NULL DEFAULT 0,
                        chunks_indexed INTEGER NOT NULL DEFAULT 0,
                        original_names JSONB NOT NULL DEFAULT '[]'::jsonb,
                        file_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
                        message TEXT NULL,
                        error TEXT NULL,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        max_retries INTEGER NOT NULL DEFAULT 3,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'upload_jobs'
                    """
                )
                columns = {row[0] for row in cur.fetchall()}

                if "file_paths" not in columns:
                    cur.execute("ALTER TABLE upload_jobs ADD COLUMN file_paths JSONB NOT NULL DEFAULT '[]'::jsonb")
                if "retry_count" not in columns:
                    cur.execute("ALTER TABLE upload_jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
                if "max_retries" not in columns:
                    cur.execute("ALTER TABLE upload_jobs ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 3")

                cur.execute("CREATE INDEX IF NOT EXISTS idx_upload_jobs_user_chat ON upload_jobs (username, chat_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_upload_jobs_status_created ON upload_jobs (status, created_at)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_upload_jobs_updated_at ON upload_jobs (updated_at)")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _normalize_json_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, tuple):
            return [str(item) for item in value]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return []
            if isinstance(payload, list):
                return [str(item) for item in payload]
        return []

    @staticmethod
    def _to_iso(value: Any) -> str:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _row_to_snapshot(self, row: Sequence[Any]) -> dict[str, Any]:
        original_names = self._normalize_json_list(row[10])
        file_paths = self._normalize_json_list(row[11])
        retry_count = int(row[14] or 0)
        max_retries = int(row[15] or 0)
        status = str(row[3])

        return {
            "job_id": str(row[0]),
            "username": str(row[1]),
            "chat_id": str(row[2]),
            "status": status,
            "stage": str(row[4]),
            "progress": int(row[5] or 0),
            "files_total": int(row[6] or 0),
            "files_processed": int(row[7] or 0),
            "chunks_total": int(row[8] or 0),
            "chunks_indexed": int(row[9] or 0),
            "original_names": original_names,
            "file_paths": file_paths,
            "message": row[12],
            "error": row[13],
            "retry_count": retry_count,
            "max_retries": max_retries,
            "can_retry": status == "failed" and retry_count < max_retries,
            "created_at": self._to_iso(row[16]),
            "updated_at": self._to_iso(row[17]),
        }
