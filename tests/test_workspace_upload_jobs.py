from pathlib import Path
from tempfile import TemporaryDirectory
import time
import uuid

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import build_container
from main import app


def _build_test_settings(base_path: Path, **overrides) -> Settings:
    settings_payload = {
        "upload_dir": str(base_path / "uploads"),
        "vector_store_path": str(base_path / "faiss"),
        "users_file_path": str(base_path / "users.json"),
        "database_path": str(base_path / "app.db"),
        "auth_secret_key": "change-me-in-production",
        "local_semantic_embeddings": False,
        "openai_api_key": "",
        "google_api_key": "",
        "groq_api_key": "",
    }
    settings_payload.update(overrides)
    return Settings(
        **settings_payload,
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


def _create_guest_headers(session_id: str | None = None) -> dict[str, str]:
    resolved_session_id = session_id or f"guest-{uuid.uuid4().hex[:24]}"
    return {"X-Guest-Session": resolved_session_id}


def _wait_for_job_terminal_status(
    client: TestClient,
    *,
    chat_id: str,
    job_id: str,
    headers: dict[str, str],
    attempts: int = 120,
    sleep_seconds: float = 0.05,
) -> dict:
    payload: dict | None = None
    for _ in range(attempts):
        status_response = client.get(
            f"/api/v1/workspace/chats/{chat_id}/upload-jobs/{job_id}",
            headers=headers,
        )
        assert status_response.status_code == 200
        payload = status_response.json()
        if payload["status"] in {"completed", "failed"}:
            break
        time.sleep(sleep_seconds)

    assert payload is not None
    return payload


def _upload_chat_files(
    client: TestClient,
    *,
    chat_id: str,
    headers: dict[str, str],
    files: list[tuple[str, tuple[str, bytes, str]]],
    duplicate_action: str | None = None,
):
    data: dict[str, str] | None = None
    if duplicate_action is not None:
        data = {"duplicate_action": duplicate_action}

    return client.post(
        f"/api/v1/workspace/chats/{chat_id}/upload",
        headers=headers,
        files=files,
        data=data,
    )


def test_workspace_upload_job_completes_and_records_documents() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
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
                final_status_payload = _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=job_id,
                    headers=headers,
                )
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


def test_workspace_upload_job_retry_flow_for_failed_job() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                headers, chat_id = _create_user_and_chat(client)

                # Corrupted XLSX payload is expected to fail in ingestion loader.
                upload_response = client.post(
                    f"/api/v1/workspace/chats/{chat_id}/upload",
                    headers=headers,
                    files=[
                        (
                            "files",
                            (
                                "broken.xlsx",
                                b"this is not a valid xlsx binary",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            ),
                        )
                    ],
                )

                assert upload_response.status_code == 200
                upload_payload = upload_response.json()
                job_id = upload_payload["job_id"]

                failed_payload = _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=job_id,
                    headers=headers,
                )
                assert failed_payload["status"] == "failed"
                assert failed_payload["can_retry"] is True
                assert failed_payload["retry_count"] == 0

                retry_response = client.post(
                    f"/api/v1/workspace/chats/{chat_id}/upload-jobs/{job_id}/retry",
                    headers=headers,
                )
                assert retry_response.status_code == 200
                retried_payload = retry_response.json()
                assert retried_payload["status"] in {"queued", "processing"}
                assert retried_payload["retry_count"] == 1

                failed_again_payload = _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=job_id,
                    headers=headers,
                )
                assert failed_again_payload["status"] == "failed"
                assert failed_again_payload["retry_count"] == 1
        finally:
            app.state.container = original_container


def test_workspace_upload_detects_duplicate_hash_without_queueing_new_job() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                headers, chat_id = _create_user_and_chat(client)

                first_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[
                        (
                            "files",
                            ("policy.md", b"# Policy\nDuplicate hash detection.", "text/markdown"),
                        )
                    ],
                )
                assert first_upload.status_code == 200
                first_job_id = first_upload.json()["job_id"]

                completed_payload = _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=first_job_id,
                    headers=headers,
                )
                assert completed_payload["status"] == "completed"

                duplicate_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[
                        (
                            "files",
                            ("policy-copy.md", b"# Policy\nDuplicate hash detection.", "text/markdown"),
                        )
                    ],
                )
                assert duplicate_upload.status_code == 200
                duplicate_payload = duplicate_upload.json()
                assert duplicate_payload["status"] == "duplicate"
                assert duplicate_payload.get("job_id") is None
                assert duplicate_payload.get("duplicates")
                assert duplicate_payload["duplicates"][0]["existing_document_id"]

                docs_response = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert docs_response.status_code == 200
                docs_payload = docs_response.json()
                assert len(docs_payload["documents"]) == 1

                jobs_response = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/upload-jobs",
                    headers=headers,
                )
                assert jobs_response.status_code == 200
                jobs_payload = jobs_response.json()
                assert len(jobs_payload["jobs"]) == 1
        finally:
            app.state.container = original_container


def test_workspace_upload_detects_duplicate_hash_while_existing_job_is_pending() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(
            base_path,
            upload_job_worker_poll_seconds=10.0,
        )

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                headers, chat_id = _create_user_and_chat(client)

                first_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[
                        (
                            "files",
                            ("pending.md", b"# Pending\nSame content pending duplicate", "text/markdown"),
                        )
                    ],
                )
                assert first_upload.status_code == 200
                first_payload = first_upload.json()
                assert first_payload["status"] in {"queued", "processing"}

                duplicate_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[
                        (
                            "files",
                            ("pending-copy.md", b"# Pending\nSame content pending duplicate", "text/markdown"),
                        )
                    ],
                )
                assert duplicate_upload.status_code == 200
                duplicate_payload = duplicate_upload.json()
                assert duplicate_payload["status"] == "duplicate"
                assert duplicate_payload.get("job_id") is None
                assert duplicate_payload.get("duplicates")
                assert duplicate_payload["duplicates"][0]["existing_document_id"].startswith("upload-job:")

                jobs_response = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/upload-jobs",
                    headers=headers,
                )
                assert jobs_response.status_code == 200
                jobs_payload = jobs_response.json()
                assert len(jobs_payload["jobs"]) == 1
        finally:
            app.state.container = original_container


def test_workspace_upload_supports_keep_both_for_duplicate_hash() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                headers, chat_id = _create_user_and_chat(client)

                first_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[("files", ("report.md", b"# Report\nRevenue 2026", "text/markdown"))],
                )
                assert first_upload.status_code == 200
                first_job_id = first_upload.json()["job_id"]
                _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=first_job_id,
                    headers=headers,
                )

                keep_both_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[("files", ("report-copy.md", b"# Report\nRevenue 2026", "text/markdown"))],
                    duplicate_action="keep_both",
                )
                assert keep_both_upload.status_code == 200
                keep_both_payload = keep_both_upload.json()
                assert keep_both_payload["status"] in {"queued", "processing"}
                second_job_id = keep_both_payload["job_id"]

                second_job_result = _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=second_job_id,
                    headers=headers,
                )
                assert second_job_result["status"] == "completed"

                docs_response = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert docs_response.status_code == 200
                docs_payload = docs_response.json()
                assert len(docs_payload["documents"]) == 2

                hashes = [doc.get("file_hash") for doc in docs_payload["documents"]]
                assert hashes[0]
                assert hashes[0] == hashes[1]
                versions = sorted(int(doc.get("version") or 1) for doc in docs_payload["documents"])
                assert versions == [1, 2]
        finally:
            app.state.container = original_container


def test_workspace_upload_replace_reindexes_without_creating_duplicate_record() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                headers, chat_id = _create_user_and_chat(client)

                first_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[("files", ("notes.md", b"# Notes\nSame content", "text/markdown"))],
                )
                assert first_upload.status_code == 200
                first_job_id = first_upload.json()["job_id"]
                _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=first_job_id,
                    headers=headers,
                )

                before_docs = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert before_docs.status_code == 200
                before_docs_payload = before_docs.json()["documents"]
                assert len(before_docs_payload) == 1
                original_doc_id = before_docs_payload[0]["document_id"]

                replace_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[("files", ("notes-replaced.md", b"# Notes\nSame content", "text/markdown"))],
                    duplicate_action="replace",
                )
                assert replace_upload.status_code == 200
                replace_payload = replace_upload.json()
                assert replace_payload["status"] in {"queued", "processing"}

                replace_job_result = _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=replace_payload["job_id"],
                    headers=headers,
                )
                assert replace_job_result["status"] == "completed"

                after_docs = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert after_docs.status_code == 200
                after_docs_payload = after_docs.json()["documents"]
                assert len(after_docs_payload) == 1
                assert after_docs_payload[0]["document_id"] != original_doc_id
                assert after_docs_payload[0]["original_name"] == "notes-replaced.md"
        finally:
            app.state.container = original_container


def test_workspace_upload_same_filename_different_content_is_not_duplicate() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                headers, chat_id = _create_user_and_chat(client)

                first_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[("files", ("plan.md", b"# Plan\nVersion A", "text/markdown"))],
                )
                assert first_upload.status_code == 200
                _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=first_upload.json()["job_id"],
                    headers=headers,
                )

                second_upload = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[("files", ("plan.md", b"# Plan\nVersion B", "text/markdown"))],
                )
                assert second_upload.status_code == 200
                second_payload = second_upload.json()
                assert second_payload["status"] in {"queued", "processing"}
                _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=second_payload["job_id"],
                    headers=headers,
                )

                docs_response = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert docs_response.status_code == 200
                docs_payload = docs_response.json()["documents"]
                assert len(docs_payload) == 2
                assert docs_payload[0]["file_hash"] != docs_payload[1]["file_hash"]
        finally:
            app.state.container = original_container


def test_workspace_delete_document_is_idempotent_for_stale_client_state() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                headers, chat_id = _create_user_and_chat(client)

                upload_response = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[
                        (
                            "files",
                            ("delete-me.md", b"# Delete me\nIdempotent delete check", "text/markdown"),
                        )
                    ],
                )
                assert upload_response.status_code == 200
                job_id = upload_response.json()["job_id"]
                _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=job_id,
                    headers=headers,
                )

                docs_response = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert docs_response.status_code == 200
                docs_payload = docs_response.json()["documents"]
                assert len(docs_payload) == 1
                document_id = docs_payload[0]["document_id"]

                first_delete = client.delete(
                    f"/api/v1/workspace/chats/{chat_id}/documents/{document_id}",
                    headers=headers,
                )
                assert first_delete.status_code == 200
                assert first_delete.json().get("ok") is True

                second_delete = client.delete(
                    f"/api/v1/workspace/chats/{chat_id}/documents/{document_id}",
                    headers=headers,
                )
                assert second_delete.status_code == 200
                assert second_delete.json().get("ok") is True
        finally:
            app.state.container = original_container


def test_workspace_delete_all_documents_clears_workspace_documents() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                headers, chat_id = _create_user_and_chat(client)

                upload_response = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=headers,
                    files=[
                        ("files", ("bulk-a.md", b"# Bulk A", "text/markdown")),
                        ("files", ("bulk-b.md", b"# Bulk B", "text/markdown")),
                    ],
                )
                assert upload_response.status_code == 200
                _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=upload_response.json()["job_id"],
                    headers=headers,
                )

                before_docs = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert before_docs.status_code == 200
                assert len(before_docs.json()["documents"]) == 2

                delete_all_response = client.delete(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert delete_all_response.status_code == 200
                assert delete_all_response.json().get("ok") is True
                assert delete_all_response.json().get("deleted_documents") == 2

                after_docs = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert after_docs.status_code == 200
                assert after_docs.json()["documents"] == []

                second_delete_all = client.delete(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=headers,
                )
                assert second_delete_all.status_code == 200
                assert second_delete_all.json().get("ok") is True
                assert second_delete_all.json().get("deleted_documents") == 0
        finally:
            app.state.container = original_container


def test_workspace_delete_messages_keeps_workspace() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                headers, chat_id = _create_user_and_chat(client)

                ask_response = client.post(
                    f"/api/v1/workspace/chats/{chat_id}/ask",
                    headers=headers,
                    json={"question": "Xin chao"},
                )
                assert ask_response.status_code == 200

                before_messages = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/messages",
                    headers=headers,
                )
                assert before_messages.status_code == 200
                assert len(before_messages.json()["messages"]) >= 1

                clear_messages = client.delete(
                    f"/api/v1/workspace/chats/{chat_id}/messages",
                    headers=headers,
                )
                assert clear_messages.status_code == 200
                assert clear_messages.json().get("ok") is True
                assert int(clear_messages.json().get("deleted_messages") or 0) >= 1

                after_messages = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/messages",
                    headers=headers,
                )
                assert after_messages.status_code == 200
                assert after_messages.json()["messages"] == []

                chats_response = client.get(
                    "/api/v1/workspace/chats",
                    headers=headers,
                )
                assert chats_response.status_code == 200
                assert any(chat["chat_id"] == chat_id for chat in chats_response.json()["chats"])
        finally:
            app.state.container = original_container


def test_workspace_guest_mode_supports_workspace_and_upload_without_login() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                guest_headers = _create_guest_headers()

                create_chat_response = client.post(
                    "/api/v1/workspace/chats",
                    headers=guest_headers,
                    json={"title": "Guest Workspace"},
                )
                assert create_chat_response.status_code == 200
                chat_id = create_chat_response.json()["chat_id"]

                chats_response = client.get("/api/v1/workspace/chats", headers=guest_headers)
                assert chats_response.status_code == 200
                assert any(chat["chat_id"] == chat_id for chat in chats_response.json()["chats"])

                upload_response = _upload_chat_files(
                    client,
                    chat_id=chat_id,
                    headers=guest_headers,
                    files=[("files", ("guest-notes.md", b"# Guest file", "text/markdown"))],
                )
                assert upload_response.status_code == 200

                job_payload = _wait_for_job_terminal_status(
                    client,
                    chat_id=chat_id,
                    job_id=upload_response.json()["job_id"],
                    headers=guest_headers,
                )
                assert job_payload["status"] == "completed"

                docs_response = client.get(
                    f"/api/v1/workspace/chats/{chat_id}/documents",
                    headers=guest_headers,
                )
                assert docs_response.status_code == 200
                assert len(docs_response.json()["documents"]) == 1

                ask_response = client.post(
                    f"/api/v1/workspace/chats/{chat_id}/ask",
                    headers=guest_headers,
                    json={"question": "Tom tat tai lieu"},
                )
                assert ask_response.status_code == 200
                assert isinstance(ask_response.json().get("answer"), str)
        finally:
            app.state.container = original_container


def test_workspace_guest_sessions_are_isolated() -> None:
    with TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        settings = _build_test_settings(base_path)

        original_container = app.state.container
        app.state.container = build_container(settings)
        try:
            with TestClient(app) as client:
                guest_headers_a = _create_guest_headers("guest-session-a123")
                guest_headers_b = _create_guest_headers("guest-session-b456")

                create_chat_response = client.post(
                    "/api/v1/workspace/chats",
                    headers=guest_headers_a,
                    json={"title": "Guest A"},
                )
                assert create_chat_response.status_code == 200
                chat_id_a = create_chat_response.json()["chat_id"]

                list_a = client.get("/api/v1/workspace/chats", headers=guest_headers_a)
                list_b = client.get("/api/v1/workspace/chats", headers=guest_headers_b)

                assert list_a.status_code == 200
                assert list_b.status_code == 200
                assert any(chat["chat_id"] == chat_id_a for chat in list_a.json()["chats"])
                assert not any(chat["chat_id"] == chat_id_a for chat in list_b.json()["chats"])
        finally:
            app.state.container = original_container
