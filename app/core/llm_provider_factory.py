from app.core.config import Settings
from app.services.interfaces.llm_provider import ILLMProvider
from app.services.llm_providers.gemini_llm_provider import GeminiLLMProvider
from app.services.llm_providers.groq_llm_provider import GroqLLMProvider
from app.services.llm_providers.local_grounded_llm_provider import LocalGroundedLLMProvider
from app.services.llm_providers.openai_llm_provider import OpenAILLMProvider


def build_llm_provider(settings: Settings) -> ILLMProvider:
    if settings.groq_api_key.strip():
        return GroqLLMProvider(
            api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            max_answer_chars=settings.max_answer_chars,
        )

    if settings.google_api_key.strip():
        return GeminiLLMProvider(
            api_key=settings.google_api_key,
            model_name=settings.gemini_model,
            max_answer_chars=settings.max_answer_chars,
        )

    if settings.openai_api_key.strip():
        return OpenAILLMProvider(
            api_key=settings.openai_api_key,
            model_name=settings.openai_model,
            max_answer_chars=settings.max_answer_chars,
        )

    return LocalGroundedLLMProvider(max_answer_chars=settings.max_answer_chars)
