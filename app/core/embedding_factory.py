import logging

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings
from app.services.embeddings.deterministic_embeddings import DeterministicEmbeddings
from app.services.embeddings.local_semantic_embeddings import LocalSemanticEmbeddings


logger = logging.getLogger(__name__)


def build_embeddings(settings: Settings) -> Embeddings:
    if settings.google_api_key.strip():
        return GoogleGenerativeAIEmbeddings(
            google_api_key=settings.google_api_key,
            model="models/gemini-embedding-001",
        )

    if settings.openai_api_key.strip():
        return OpenAIEmbeddings(
            model=settings.embeddings_model,
            api_key=settings.openai_api_key,
        )

    if settings.local_semantic_embeddings:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            logger.warning(
                "local_semantic_embeddings_enabled_but_missing_dependency_fallback_to_deterministic"
            )
            return DeterministicEmbeddings()
        return LocalSemanticEmbeddings(
            model_name=settings.local_semantic_model_name,
            normalize_embeddings=settings.local_semantic_normalize_embeddings,
        )

    return DeterministicEmbeddings()
