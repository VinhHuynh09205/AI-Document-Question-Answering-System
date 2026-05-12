from __future__ import annotations

import logging

from langchain_core.embeddings import Embeddings


logger = logging.getLogger(__name__)

_FALLBACK_ERROR_HINTS = (
    "resource_exhausted",
    "quota",
    "rate limit",
    "429",
    "embed_content_free_tier_requests",
)


class ResilientEmbeddings(Embeddings):
    """Wrap embeddings provider and switch to fallback on quota/rate-limit failures."""

    def __init__(self, primary: Embeddings, fallback: Embeddings) -> None:
        self._primary = primary
        self._fallback = fallback
        self._fallback_active = False

    @property
    def model_name(self) -> str:
        active = self._active_provider()
        for attr_name in ("model_name", "_model_name", "model"):
            value = getattr(active, attr_name, "")
            if value:
                return str(value)
        return "unknown"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self._fallback_active:
            return self._fallback.embed_documents(texts)

        try:
            return self._primary.embed_documents(texts)
        except Exception as exc:
            if not self._should_fallback(exc):
                raise
            self._activate_fallback(exc)
            return self._fallback.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if self._fallback_active:
            return self._fallback.embed_query(text)

        try:
            return self._primary.embed_query(text)
        except Exception as exc:
            if not self._should_fallback(exc):
                raise
            self._activate_fallback(exc)
            return self._fallback.embed_query(text)

    def _active_provider(self) -> Embeddings:
        return self._fallback if self._fallback_active else self._primary

    def _activate_fallback(self, exc: Exception) -> None:
        if self._fallback_active:
            return

        self._fallback_active = True
        logger.warning(
            "embedding_provider_fallback_activated primary=%s fallback=%s error_type=%s",
            self._primary.__class__.__name__,
            self._fallback.__class__.__name__,
            type(exc).__name__,
        )

    @staticmethod
    def _should_fallback(exc: Exception) -> bool:
        message = str(exc or "").casefold()
        if not message:
            return False
        return any(hint in message for hint in _FALLBACK_ERROR_HINTS)
