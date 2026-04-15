from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import build_container
from main import app


def test_upload_accepts_markdown_and_csv() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        upload_dir = base_path / "uploads"
        vector_store_dir = base_path / "faiss"
        users_file = base_path / "users.json"
        settings = Settings(
            upload_dir=str(upload_dir),
            vector_store_path=str(vector_store_dir),
            users_file_path=str(users_file),
            database_path=str(base_path / "app.db"),
            supported_upload_extensions=".pdf,.docx,.txt,.md,.csv",
            openai_api_key="",
            google_api_key="",
            groq_api_key="",
            local_semantic_embeddings=False,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/upload",
                files=[
                    ("files", ("notes.md", b"# Heading\nBody", "text/markdown")),
                    ("files", ("table.csv", b"name,age\nAna,30", "text/csv")),
                ],
            )
        finally:
            app.state.container = original_container

        assert response.status_code == 200
        payload = response.json()
        assert payload["message"] == "Files uploaded successfully"
        assert payload["files_processed"] == 2
        assert payload["chunks_indexed"] >= 2
        assert (vector_store_dir / "index.faiss").exists()
        assert (vector_store_dir / "documents.json").exists()


def test_upload_rejects_unsupported_extension() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        upload_dir = base_path / "uploads"
        vector_store_dir = base_path / "faiss"
        users_file = base_path / "users.json"
        settings = Settings(
            upload_dir=str(upload_dir),
            vector_store_path=str(vector_store_dir),
            users_file_path=str(users_file),
            database_path=str(base_path / "app.db"),
            supported_upload_extensions=".pdf,.docx,.txt,.md,.csv",
            openai_api_key="",
            google_api_key="",
            groq_api_key="",
            local_semantic_embeddings=False,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/upload",
                files=[
                    (
                        "files",
                        ("malware.exe", b"binary-data", "application/octet-stream"),
                    )
                ],
            )
        finally:
            app.state.container = original_container

        assert response.status_code == 400
        payload = response.json()
        assert "Unsupported file type" in payload["detail"]
