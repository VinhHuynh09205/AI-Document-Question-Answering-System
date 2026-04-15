from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import build_container
from app.services.qa_constants import FALLBACK_ANSWER
from main import app


def test_ask_returns_fallback_when_no_context() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = Settings(
            upload_dir=str(base_path / "uploads"),
            vector_store_path=str(base_path / "faiss"),
            users_file_path=str(base_path / "users.json"),
            database_path=str(base_path / "app.db"),
            openai_api_key="",
            google_api_key="",
            groq_api_key="",
            local_semantic_embeddings=False,
            top_k=3,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            response = client.post("/api/v1/ask", json={"question": "Tai lieu noi gi?"})
        finally:
            app.state.container = original_container

        assert response.status_code == 200
        payload = response.json()
        assert payload["answer"] == FALLBACK_ANSWER
        assert payload["sources"] == []


def test_ask_returns_grounded_answer_after_upload() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = Settings(
            upload_dir=str(base_path / "uploads"),
            vector_store_path=str(base_path / "faiss"),
            users_file_path=str(base_path / "users.json"),
            database_path=str(base_path / "app.db"),
            openai_api_key="",
            google_api_key="",
            groq_api_key="",
            local_semantic_embeddings=False,
            top_k=3,
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
            ask_response = client.post(
                "/api/v1/ask",
                json={"question": "FastAPI la gi?"},
            )
        finally:
            app.state.container = original_container

        assert upload_response.status_code == 200

        assert ask_response.status_code == 200
        payload = ask_response.json()
        assert payload["answer"] != FALLBACK_ANSWER
        assert "FastAPI" in payload["answer"]
        assert payload["sources"]
        assert "knowledge.md" in payload["sources"][0]


def test_ask_unrelated_question_returns_fallback() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = Settings(
            upload_dir=str(base_path / "uploads"),
            vector_store_path=str(base_path / "faiss"),
            users_file_path=str(base_path / "users.json"),
            database_path=str(base_path / "app.db"),
            openai_api_key="",
            google_api_key="",
            groq_api_key="",
            local_semantic_embeddings=False,
            top_k=3,
            min_context_token_overlap=0.2,
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
            ask_response = client.post(
                "/api/v1/ask",
                json={"question": "Thoi tiet hom nay the nao?"},
            )
        finally:
            app.state.container = original_container

        assert upload_response.status_code == 200
        assert ask_response.status_code == 200
        payload = ask_response.json()
        assert len(payload["answer"]) > 0
        assert payload["answer"] != FALLBACK_ANSWER
