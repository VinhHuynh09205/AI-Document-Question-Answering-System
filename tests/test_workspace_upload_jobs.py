from pathlib import Path
from tempfile import TemporaryDirectory
import time
import uuid

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import build_container
from main import app


def _build_test_settings(base_path: Path) -> Settings:
    return Settings(
        upload_dir=str(base_path / "uploads"),
        vector_store_path=str(base_path / "faiss"),
        users_file_path=str(base_path / "users.json"),
        database_path=str(base_path / "app.db"),
        auth_secret_key="change-me-in-production",
        local_semantic_embeddings=False,
        openai_api_key="",
        google_api_key="",
        groq_api_key="",
    )


def _create_user_and_chat(client: TestClient) -> tuple[dict[str, str], str]:
    username = f"upload-job-{uuid.uuid4().hex[:8]}"
    password = "StrongPass123"

    register_response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    assert register_response.status_code == 200
    token = register_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_chat_response = client.post(
        "/api/v1/workspace/chats",
        json={"title": "Upload Job Test"},
        headers=headers,
    )
    assert create_chat_response.status_code == 200
    chat_id = create_chat_response.json()["chat_id"]

    return headers, chat_id


def test_workspace_upload_job_completes_and_records_documents() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            headers, chat_id = _create_user_and_chat(client)

            upload_response = client.post(
                f"/api/v1/workspace/chats/{chat_id}/upload",
                headers=headers,
                files=[
                    (
                        "files",
                        ("notes.md", b"# Upload job test\nThis is a short document.", "text/markdown"),
                    )
                ],
            )

            assert upload_response.status_code == 200
            upload_payload = upload_response.json()
            assert upload_payload["message"] == "Files accepted for background indexing"
            assert isinstance(upload_payload.get("job_id"), str)
            assert upload_payload["job_id"]
            assert upload_payload.get("status") in {"queued", "processing"}

            job_id = upload_payload["job_id"]
            final_status_payload: dict | None = None
            for _ in range(80):
                status_response = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/upload-jobs/{job_id}",
                    headers=headers,
                )
                assert status_response.status_code == 200
                final_status_payload = status_response.json()
                if final_status_payload["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.05)

            assert final_status_payload is not None
            assert final_status_payload["status"] == "completed", final_status_payload.get("error")
            assert final_status_payload["progress"] == 100
            assert final_status_payload["files_processed"] == 1
            assert final_status_payload["chunks_indexed"] >= 1

            docs_response = client.get(
                f"/api/v1/workspace/chats/{chat_id}/documents",
                headers=headers,
            )
            assert docs_response.status_code == 200
            docs_payload = docs_response.json()
            assert len(docs_payload["documents"]) == 1
        finally:
            app.state.container = original_container
