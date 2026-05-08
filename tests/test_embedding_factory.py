import sys

from langchain_core.embeddings import Embeddings

from app.core import embedding_factory
from app.core.config import Settings
from app.services.embeddings.deterministic_embeddings import DeterministicEmbeddings


class _DummyEmbeddings(Embeddings):
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0]


def test_build_embeddings_prefers_local_when_enabled(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", object())
    monkeypatch.setattr(embedding_factory, "LocalSemanticEmbeddings", _DummyEmbeddings)

    settings = Settings(
        local_semantic_embeddings_enabled=True,
        local_semantic_embeddings=False,
        google_api_key="google-key",
        openai_api_key="openai-key",
        embedding_device="cpu",
    )

    provider = embedding_factory.build_embeddings(settings)

    assert isinstance(provider, _DummyEmbeddings)
    assert provider.kwargs["device"] == "cpu"


def test_build_embeddings_uses_google_when_local_disabled(monkeypatch) -> None:
    monkeypatch.setattr(embedding_factory, "GoogleGenerativeAIEmbeddings", _DummyEmbeddings)

    settings = Settings(
        local_semantic_embeddings_enabled=False,
        local_semantic_embeddings=False,
        google_api_key="google-key",
        openai_api_key="openai-key",
    )

    provider = embedding_factory.build_embeddings(settings)

    assert isinstance(provider, _DummyEmbeddings)
    assert provider.kwargs["google_api_key"] == "google-key"


def test_build_embeddings_falls_back_to_deterministic_without_remote_keys() -> None:
    settings = Settings(
        local_semantic_embeddings_enabled=False,
        local_semantic_embeddings=False,
        google_api_key="",
        openai_api_key="",
    )

    provider = embedding_factory.build_embeddings(settings)

    assert isinstance(provider, DeterministicEmbeddings)