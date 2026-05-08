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


def test_legacy_upload_replace_mode_does_not_clear_workspace_vectors() -> None:
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
            replace_existing_documents_on_upload=True,
            openai_api_key="",
            google_api_key="",
            groq_api_key="",
            local_semantic_embeddings=False,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            workspace_service = app.state.container.workspace_service
            ingestion_service = app.state.container.ingestion_service
            vector_store_repository = app.state.container.vector_store_repository

            chat = workspace_service.create_chat(username="workspace-user", title="Workspace Chat")
            workspace_doc_path = upload_dir / "workspace-note.md"
            workspace_doc_path.parent.mkdir(parents=True, exist_ok=True)
            workspace_doc_path.write_text(
                "Workspace scoped content for retrieval verification.",
                encoding="utf-8",
            )

            ingestion_service.ingest(
                [workspace_doc_path],
                {"owner": "workspace-user", "chat_id": chat.chat_id},
            )

            before = vector_store_repository.similarity_search(
                query="workspace scoped content",
                k=5,
                metadata_filter={"owner": "workspace-user", "chat_id": chat.chat_id},
            )
            assert before

            client = TestClient(app)
            response = client.post(
                "/api/v1/upload",
                files=[
                    (
                        "files",
                        (
                            "legacy.md",
                            b"Legacy upload endpoint content.",
                            "text/markdown",
                        ),
                    )
                ],
            )

            after = vector_store_repository.similarity_search(
                query="workspace scoped content",
                k=5,
                metadata_filter={"owner": "workspace-user", "chat_id": chat.chat_id},
            )
        finally:
            app.state.container = original_container

        assert response.status_code == 200
        assert after
