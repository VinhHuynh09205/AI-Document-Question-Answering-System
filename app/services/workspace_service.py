from pathlib import Path
from typing import Sequence

from app.models.entities import ChatMessage, ChatSession, StoredDocument
from app.repositories.interfaces.workspace_repository import IWorkspaceRepository
from app.services.interfaces.workspace_service import IWorkspaceService


class WorkspaceService(IWorkspaceService):
    def __init__(self, workspace_repository: IWorkspaceRepository) -> None:
        self._workspace_repository = workspace_repository

    def create_chat(self, username: str, title: str) -> ChatSession:
        clean_title = title.strip() or "Đoạn chat mới"
        return self._workspace_repository.create_chat(username=username, title=clean_title)

    def list_chats(self, username: str) -> list[ChatSession]:
        return self._workspace_repository.list_chats(username)

    def ensure_chat(self, username: str, chat_id: str) -> ChatSession:
        chat = self._workspace_repository.get_chat(username, chat_id)
        if chat is None:
            raise ValueError("Chat not found")
        return chat

    def record_documents(
        self,
        username: str,
        chat_id: str,
        saved_paths: Sequence[Path],
        original_names: Sequence[str],
        *,
        file_hashes: Sequence[str] | None = None,
        file_sizes: Sequence[int] | None = None,
    ) -> list[StoredDocument]:
        records: list[StoredDocument] = []
        safe_hashes = list(file_hashes or [])
        safe_sizes = list(file_sizes or [])

        for index, (path, original_name) in enumerate(zip(saved_paths, original_names, strict=False)):
            file_hash = safe_hashes[index] if index < len(safe_hashes) else None
            file_size = safe_sizes[index] if index < len(safe_sizes) else None
            records.append(
                self._workspace_repository.add_document(
                    username=username,
                    chat_id=chat_id,
                    original_name=original_name,
                    stored_path=str(path),
                    file_hash=file_hash,
                    file_size=file_size,
                )
            )
        return records

    def get_document(self, username: str, document_id: str) -> StoredDocument | None:
        return self._workspace_repository.get_document(username=username, document_id=document_id)

    def find_document_by_hash(self, username: str, chat_id: str, file_hash: str) -> StoredDocument | None:
        normalized_hash = str(file_hash or "").strip().lower()
        if not normalized_hash:
            return None
        return self._workspace_repository.find_document_by_hash(
            username=username,
            chat_id=chat_id,
            file_hash=normalized_hash,
        )

    def list_documents(self, username: str, chat_id: str) -> list[StoredDocument]:
        return self._workspace_repository.list_documents(username, chat_id)

    def add_message(self, username: str, chat_id: str, role: str, content: str) -> ChatMessage:
        return self._workspace_repository.add_message(
            username=username,
            chat_id=chat_id,
            role=role,
            content=content,
        )

    def list_messages(self, username: str, chat_id: str, limit: int = 200) -> list[ChatMessage]:
        return self._workspace_repository.list_messages(username, chat_id, limit=limit)

    def rename_chat(self, username: str, chat_id: str, new_title: str) -> ChatSession:
        clean_title = new_title.strip()
        if not clean_title:
            raise ValueError("Title cannot be empty")
        chat = self._workspace_repository.rename_chat(username, chat_id, clean_title)
        if chat is None:
            raise ValueError("Chat not found")
        return chat

    def delete_chat(self, username: str, chat_id: str) -> bool:
        return self._workspace_repository.delete_chat(username, chat_id)

    def delete_documents_for_chat(self, username: str, chat_id: str) -> int:
        return self._workspace_repository.delete_documents_for_chat(username, chat_id)

    def delete_messages_for_chat(self, username: str, chat_id: str) -> int:
        return self._workspace_repository.delete_messages_for_chat(username, chat_id)

    def rename_document(self, username: str, document_id: str, new_name: str) -> StoredDocument:
        clean_name = new_name.strip()
        if not clean_name:
            raise ValueError("Name cannot be empty")
        doc = self._workspace_repository.rename_document(username, document_id, clean_name)
        if doc is None:
            raise ValueError("Document not found")
        return doc

    def delete_document(self, username: str, document_id: str) -> bool:
        return self._workspace_repository.delete_document(username, document_id)
