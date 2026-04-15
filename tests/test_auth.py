from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import build_container
from main import app


def test_register_and_login_success() -> None:
    with TemporaryDirectory() as tmp_dir:
        users_file = Path(tmp_dir) / "users.json"
        settings = Settings(
            users_file_path=str(users_file),
            database_path=str(Path(tmp_dir) / "app.db"),
            auth_secret_key="test-secret",
            enable_registration=True,
            local_semantic_embeddings=False,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            register_response = client.post(
                "/api/v1/auth/register",
                json={"username": "alice", "password": "StrongPass123"},
            )
            login_response = client.post(
                "/api/v1/auth/login",
                json={"username": "alice", "password": "StrongPass123"},
            )
        finally:
            app.state.container = original_container

    assert register_response.status_code == 200
    register_payload = register_response.json()
    assert register_payload["token_type"] == "bearer"
    assert isinstance(register_payload["access_token"], str)
    assert register_payload["access_token"]

    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["token_type"] == "bearer"
    assert isinstance(login_payload["access_token"], str)
    assert login_payload["access_token"]


def test_register_returns_403_when_disabled() -> None:
    with TemporaryDirectory() as tmp_dir:
        users_file = Path(tmp_dir) / "users.json"
        settings = Settings(
            users_file_path=str(users_file),
            database_path=str(Path(tmp_dir) / "app.db"),
            auth_secret_key="test-secret",
            enable_registration=False,
            local_semantic_embeddings=False,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/auth/register",
                json={"username": "bob", "password": "StrongPass123"},
            )
        finally:
            app.state.container = original_container

    assert response.status_code == 403
    payload = response.json()
    assert payload["detail"] == "Registration is disabled"


def test_login_returns_401_for_invalid_credentials() -> None:
    with TemporaryDirectory() as tmp_dir:
        users_file = Path(tmp_dir) / "users.json"
        settings = Settings(
            users_file_path=str(users_file),
            database_path=str(Path(tmp_dir) / "app.db"),
            auth_secret_key="test-secret",
            enable_registration=True,
            local_semantic_embeddings=False,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "missing", "password": "StrongPass123"},
            )
        finally:
            app.state.container = original_container

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Invalid username or password"
