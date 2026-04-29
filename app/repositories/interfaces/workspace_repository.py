from abc import ABC, abstractmethod

from app.models.entities import ChatMessage, ChatSession, StoredDocument


class IWorkspaceRepository(ABC):
    @abstractmethod
    def create_chat(self, username: str, title: str) -> ChatSession:
        raise NotImplementedError

    @abstractmethod
    def get_chat(self, username: str, chat_id: str) -> ChatSession | None:
        raise NotImplementedError

    @abstractmethod
    def list_chats(self, username: str) -> list[ChatSession]:
        raise NotImplementedError

    @abstractmethod
    def add_document(
        self,
        username: str,
        chat_id: str,
        original_name: str,
        stored_path: str,
        *,
        file_hash: str | None = None,
        file_size: int | None = None,
        version: int | None = None,
    ) -> StoredDocument:
        raise NotImplementedError

    @abstractmethod
    def get_document(self, username: str, document_id: str) -> StoredDocument | None:
        raise NotImplementedError

    @abstractmethod
    def find_document_by_hash(self, username: str, chat_id: str, file_hash: str) -> StoredDocument | None:
        raise NotImplementedError

    @abstractmethod
    def list_documents(self, username: str, chat_id: str) -> list[StoredDocument]:
        raise NotImplementedError

    @abstractmethod
    def add_message(self, username: str, chat_id: str, role: str, content: str) -> ChatMessage:
        raise NotImplementedError

    @abstractmethod
    def list_messages(self, username: str, chat_id: str, limit: int = 200) -> list[ChatMessage]:
        raise NotImplementedError

    @abstractmethod
    def rename_chat(self, username: str, chat_id: str, new_title: str) -> ChatSession | None:
        raise NotImplementedError

    @abstractmethod
    def delete_chat(self, username: str, chat_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_documents_for_chat(self, username: str, chat_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def delete_messages_for_chat(self, username: str, chat_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def rename_document(self, username: str, document_id: str, new_name: str) -> StoredDocument | None:
        raise NotImplementedError

    @abstractmethod
    def delete_document(self, username: str, document_id: str) -> bool:
        raise NotImplementedError
