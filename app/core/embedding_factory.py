import logging

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings
from app.services.embeddings.deterministic_embeddings import DeterministicEmbeddings
from app.services.embeddings.local_semantic_embeddings import LocalSemanticEmbeddings
from app.services.embeddings.resilient_embeddings import ResilientEmbeddings


logger = logging.getLogger(__name__)


def build_embeddings(settings: Settings) -> Embeddings:
    if settings.use_local_semantic_embeddings():
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            logger.warning(
                "local_semantic_embeddings_enabled_but_missing_dependency_fallback_to_deterministic"
            )
            return DeterministicEmbeddings()

        model_name = settings.get_local_embedding_model()
        logger.info(
            "embedding_provider_selected provider=local_semantic model=%s device=%s batch_size=%s",
            model_name,
            settings.embedding_device,
            settings.embedding_batch_size,
        )
        return LocalSemanticEmbeddings(
            model_name=model_name,
            normalize_embeddings=settings.local_semantic_normalize_embeddings,
            device=settings.embedding_device,
            batch_size=settings.embedding_batch_size,
            fallback_models=[
                "BAAI/bge-small-en-v1.5",
                "BAAI/bge-base-en-v1.5",
                "all-MiniLM-L6-v2",
            ],
        )

    if settings.google_api_key.strip():
        primary = GoogleGenerativeAIEmbeddings(
            google_api_key=settings.google_api_key,
            model="models/gemini-embedding-001",
        )

        if settings.openai_api_key.strip():
            fallback: Embeddings = OpenAIEmbeddings(
                model=settings.embeddings_model,
                api_key=settings.openai_api_key,
            )
            fallback_provider = "openai"
        else:
            fallback = DeterministicEmbeddings()
            fallback_provider = "deterministic"

        logger.info(
            "embedding_provider_selected provider=google model=models/gemini-embedding-001 fallback=%s",
            fallback_provider,
        )
        return ResilientEmbeddings(primary=primary, fallback=fallback)

    if settings.openai_api_key.strip():
        logger.info("embedding_provider_selected provider=openai model=%s", settings.embeddings_model)
        return OpenAIEmbeddings(
            model=settings.embeddings_model,
            api_key=settings.openai_api_key,
        )

    logger.info("embedding_provider_selected provider=deterministic")
    return DeterministicEmbeddings()
