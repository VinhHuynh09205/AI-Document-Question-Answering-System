from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import build_container
from main import app


def test_health_includes_request_id_and_metrics_snapshot() -> None:
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
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            health_response = client.get("/api/v1/health")
            metrics_response = client.get("/api/v1/metrics")
        finally:
            app.state.container = original_container

        assert health_response.status_code == 200
        assert health_response.headers.get("X-Request-ID")

        assert metrics_response.status_code == 200
        payload = metrics_response.json()
        assert payload["total_requests"] >= 1
        assert payload["endpoint_counts"]


def test_ask_rate_limit_enforced() -> None:
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
            rate_limit_window_seconds=120,
            ask_rate_limit_per_window=1,
            upload_rate_limit_per_window=30,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            first_response = client.post("/api/v1/ask", json={"question": "FastAPI la gi?"})
            second_response = client.post("/api/v1/ask", json={"question": "FastAPI la gi?"})
        finally:
            app.state.container = original_container

        assert first_response.status_code == 200
        assert second_response.status_code == 429
        assert second_response.headers.get("Retry-After")
