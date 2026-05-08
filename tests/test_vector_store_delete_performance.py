from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.repositories.faiss_vector_store_repository import FaissVectorStoreRepository
from app.services.runtime_metrics import RuntimeMetrics


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


def test_keyword_search_and_embedding_cache_metrics_are_recorded() -> None:
    embeddings = CountingEmbeddings()
    metrics = RuntimeMetrics()

    with TemporaryDirectory() as tmp_dir:
        repository = FaissVectorStoreRepository(
            index_dir=Path(tmp_dir),
            embeddings=embeddings,
            runtime_metrics=metrics,
            embedding_cache_enabled=True,
        )

        repository.add_documents(
            [
                Document(
                    page_content="alpha contract payment schedule",
                    metadata={"source": "doc-a.txt", "owner": "user-a"},
                ),
                Document(
                    page_content="beta delivery delay penalty clause",
                    metadata={"source": "doc-b.txt", "owner": "user-a"},
                ),
            ]
        )
        first_call_count = embeddings.embed_documents_calls

        repository.add_documents(
            [
                Document(
                    page_content="alpha contract payment schedule",
                    metadata={"source": "doc-a-duplicate.txt", "owner": "user-a"},
                )
            ]
        )

        assert embeddings.embed_documents_calls == first_call_count

        keyword_results = repository.keyword_search("payment contract", k=3)
        assert keyword_results
        assert float(keyword_results[0].metadata.get("keyword_score", 0.0)) > 0

        snapshot = metrics.snapshot()
        assert snapshot["counters"].get("cache_hits", 0) >= 1
        assert snapshot["counters"].get("cache_misses", 0) >= 2
