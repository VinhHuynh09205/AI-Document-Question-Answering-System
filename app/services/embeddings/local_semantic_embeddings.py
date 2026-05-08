import logging
from threading import Lock

from langchain_core.embeddings import Embeddings


logger = logging.getLogger(__name__)

_DEFAULT_LOCAL_EMBEDDING_MODELS = [
    "BAAI/bge-small-en-v1.5",
    "BAAI/bge-base-en-v1.5",
    "all-MiniLM-L6-v2",
]
_MODEL_CACHE_LOCK = Lock()
_MODEL_CACHE: dict[tuple[str, str], object] = {}


class LocalSemanticEmbeddings(Embeddings):
    """Semantic embeddings backed by cached local SentenceTransformer models."""

    def __init__(
        self,
        model_name: str,
        normalize_embeddings: bool = True,
        *,
        device: str = "auto",
        batch_size: int = 64,
        fallback_models: list[str] | None = None,
    ) -> None:
        self._configured_model_name = str(model_name or "").strip()
        self._normalize_embeddings = normalize_embeddings
        self._device = str(device or "auto").strip().lower() or "auto"
        self._batch_size = max(1, int(batch_size))
        self._fallback_models = list(fallback_models or _DEFAULT_LOCAL_EMBEDDING_MODELS)

        self._model = None
        self._active_model_name = ""
        self._active_device = ""

    @property
    def model_name(self) -> str:
        return self._active_model_name or self._configured_model_name

    @property
    def device(self) -> str:
        return self._active_device or self._resolve_device()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._get_model()
        vectors = model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=self._normalize_embeddings,
            batch_size=self._batch_size,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else []

    def _get_model(self):
        if self._model is None:
            self._model, self._active_model_name, self._active_device = self._load_model_with_fallback()

        return self._model

    def _load_model_with_fallback(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - runtime guard
            raise RuntimeError(
                "sentence-transformers is required for local semantic embeddings"
            ) from exc

        device = self._resolve_device()
        candidates = self._build_model_candidates()
        last_exception: Exception | None = None

        for candidate in candidates:
            cache_key = (candidate, device)
            with _MODEL_CACHE_LOCK:
                cached = _MODEL_CACHE.get(cache_key)
                if cached is not None:
                    logger.info(
                        "local_embedding_model_reused model=%s device=%s",
                        candidate,
                        device,
                    )
                    return cached, candidate, device

            try:
                model = SentenceTransformer(candidate, device=device)
            except Exception as exc:  # pragma: no cover - runtime guard
                last_exception = exc
                logger.warning(
                    "local_embedding_model_load_failed model=%s device=%s error_type=%s",
                    candidate,
                    device,
                    type(exc).__name__,
                )
                continue

            with _MODEL_CACHE_LOCK:
                _MODEL_CACHE[cache_key] = model

            logger.info(
                "local_embedding_model_loaded model=%s device=%s batch_size=%s",
                candidate,
                device,
                self._batch_size,
            )
            return model, candidate, device

        if last_exception is not None:
            raise RuntimeError("Unable to load any local embedding model") from last_exception
        raise RuntimeError("No local embedding model candidates were provided")

    def _build_model_candidates(self) -> list[str]:
        candidates: list[str] = []

        def _add(value: str) -> None:
            candidate = str(value or "").strip()
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        _add(self._configured_model_name)
        for fallback in self._fallback_models:
            _add(fallback)

        return candidates

    def _resolve_device(self) -> str:
        raw_device = self._device
        if raw_device not in {"auto", "cpu", "cuda", "mps"}:
            return "cpu"

        if raw_device != "auto":
            return raw_device

        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except Exception:
            return "cpu"

        return "cpu"
