from fastapi.testclient import TestClient

from main import app


def test_root_serves_web_ui() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "ChatBoxAI" in response.text
