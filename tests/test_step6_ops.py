from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import build_container
from main import app


def test_security_headers_and_readiness_endpoint() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = Settings(
            upload_dir=str(base_path / "uploads"),
            vector_store_path=str(base_path / "faiss"),
            vector_backup_dir=str(base_path / "faiss_backups"),
            users_file_path=str(base_path / "users.json"),
            database_path=str(base_path / "app.db"),
            openai_api_key="",
            google_api_key="",
            groq_api_key="",
            local_semantic_embeddings=False,
            enable_security_headers=True,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            response = client.get("/api/v1/health/ready")
        finally:
            app.state.container = original_container

        assert response.status_code == 200
        assert response.json()["status"] in {"ok", "degraded"}
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


def test_vector_backup_and_restore_latest() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = Settings(
            upload_dir=str(base_path / "uploads"),
            vector_store_path=str(base_path / "faiss"),
            vector_backup_dir=str(base_path / "faiss_backups"),
            users_file_path=str(base_path / "users.json"),
            database_path=str(base_path / "app.db"),
            openai_api_key="",
            google_api_key="",
            groq_api_key="",
            local_semantic_embeddings=False,
            rate_limit_window_seconds=60,
            upload_rate_limit_per_window=100,
            ask_rate_limit_per_window=100,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)

            upload_response = client.post(
                "/api/v1/upload",
                files=[
                    (
                        "files",
                        (
                            "knowledge.md",
                            b"FastAPI la framework Python de xay dung API nhanh.",
                            "text/markdown",
                        ),
                    )
                ],
            )
            backup_response = client.post("/api/v1/ops/vector/backup")
            restore_response = client.post("/api/v1/ops/vector/restore-latest")
            status_response = client.get("/api/v1/ops/vector/status")
        finally:
            app.state.container = original_container

        assert upload_response.status_code == 200

        assert backup_response.status_code == 200
        backup_payload = backup_response.json()
        assert backup_payload["backed_up"] is True
        assert backup_payload["document_count"] >= 1

        assert restore_response.status_code == 200
        restore_payload = restore_response.json()
        assert restore_payload["restored"] is True
        assert restore_payload["document_count"] >= 1

        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["document_count"] >= 1
