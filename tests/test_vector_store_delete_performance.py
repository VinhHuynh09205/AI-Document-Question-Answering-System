from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.repositories.faiss_vector_store_repository import FaissVectorStoreRepository


class CountingEmbeddings(Embeddings):
    def __init__(self) -> None:
        self.embed_documents_calls = 0
        self.embed_query_calls = 0

    @staticmethod
    def _embed_text(text: str) -> list[float]:
        normalized = str(text or "")
        length = float(len(normalized))
        checksum = float(sum(ord(char) for char in normalized) % 997)
        return [length, checksum, length + checksum]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embed_documents_calls += 1
        return [self._embed_text(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.embed_query_calls += 1
        return self._embed_text(text)


def test_delete_documents_by_metadata_reuses_existing_vectors() -> None:
    embeddings = CountingEmbeddings()

    with TemporaryDirectory() as tmp_dir:
        repository = FaissVectorStoreRepository(
            index_dir=Path(tmp_dir),
            embeddings=embeddings,
        )

        repository.add_documents(
            [
                Document(
                    page_content="chunk one",
                    metadata={"owner": "user-a", "chat_id": "chat-1", "source": "doc-a.txt"},
                ),
                Document(
                    page_content="chunk two",
                    metadata={"owner": "user-a", "chat_id": "chat-1", "source": "doc-a.txt"},
                ),
                Document(
                    page_content="chunk three",
                    metadata={"owner": "user-a", "chat_id": "chat-2", "source": "doc-b.txt"},
                ),
            ]
        )

        embeddings.embed_documents_calls = 0

        removed = repository.delete_documents_by_metadata(
            {"owner": "user-a", "chat_id": "chat-1", "source": "doc-a.txt"}
        )

        assert removed == 2
        assert repository.document_count() == 1
        assert embeddings.embed_documents_calls == 0

        remaining_documents = repository.similarity_search(
            query="chunk",
            k=5,
            metadata_filter={"owner": "user-a", "chat_id": "chat-2"},
        )
        assert len(remaining_documents) == 1
        assert remaining_documents[0].metadata["source"] == "doc-b.txt"
