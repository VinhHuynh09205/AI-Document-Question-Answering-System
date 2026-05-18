import sys

from langchain_core.embeddings import Embeddings

from app.core import embedding_factory
from app.core.config import DEFAULT_LOCAL_EMBEDDING_MODEL, Settings
from app.services.embeddings.deterministic_embeddings import DeterministicEmbeddings
from app.services.embeddings.resilient_embeddings import ResilientEmbeddings


class _DummyEmbeddings(Embeddings):
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0]


class _QuotaFailingEmbeddings(Embeddings):
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("429 RESOURCE_EXHAUSTED: embed_content_free_tier_requests")

    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("429 RESOURCE_EXHAUSTED: embed_content_free_tier_requests")


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
    assert provider.kwargs["model_name"] == DEFAULT_LOCAL_EMBEDDING_MODEL
    assert provider.kwargs["device"] == "cpu"


def test_default_local_embedding_model_is_multilingual_minilm_l12() -> None:
    settings = Settings(
        local_semantic_embeddings_enabled=True,
        local_semantic_embeddings=True,
        google_api_key="",
        openai_api_key="",
    )

    assert settings.get_local_embedding_model() == DEFAULT_LOCAL_EMBEDDING_MODEL


def test_build_embeddings_uses_google_when_local_disabled(monkeypatch) -> None:
    monkeypatch.setattr(embedding_factory, "GoogleGenerativeAIEmbeddings", _DummyEmbeddings)

    settings = Settings(
        local_semantic_embeddings_enabled=False,
        local_semantic_embeddings=False,
        google_api_key="google-key",
        openai_api_key="openai-key",
    )

    provider = embedding_factory.build_embeddings(settings)

    assert isinstance(provider, ResilientEmbeddings)
    assert provider._primary.kwargs["google_api_key"] == "google-key"


def test_google_embeddings_fallback_to_deterministic_on_quota_error(monkeypatch) -> None:
    monkeypatch.setattr(embedding_factory, "GoogleGenerativeAIEmbeddings", _QuotaFailingEmbeddings)

    settings = Settings(
        local_semantic_embeddings_enabled=False,
        local_semantic_embeddings=False,
        google_api_key="google-key",
        openai_api_key="",
    )

    provider = embedding_factory.build_embeddings(settings)

    assert isinstance(provider, ResilientEmbeddings)
    vectors = provider.embed_documents(["tai lieu mau"])
    assert len(vectors) == 1
    assert len(vectors[0]) > 0
    assert provider._fallback_active is True


def test_build_embeddings_falls_back_to_deterministic_without_remote_keys() -> None:
    settings = Settings(
        local_semantic_embeddings_enabled=False,
        local_semantic_embeddings=False,
        google_api_key="",
        openai_api_key="",
    )

    provider = embedding_factory.build_embeddings(settings)

    assert isinstance(provider, DeterministicEmbeddings)
