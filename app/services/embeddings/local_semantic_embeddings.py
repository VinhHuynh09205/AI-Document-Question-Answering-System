from langchain_core.embeddings import Embeddings


class LocalSemanticEmbeddings(Embeddings):
    """Semantic embeddings backed by a local SentenceTransformer model."""

    def __init__(self, model_name: str, normalize_embeddings: bool = True) -> None:
        self._model_name = model_name
        self._normalize_embeddings = normalize_embeddings
        self._model = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._get_model()
        vectors = model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=self._normalize_embeddings,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else []

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - runtime guard
                raise RuntimeError(
                    "sentence-transformers is required for local semantic embeddings"
                ) from exc

            self._model = SentenceTransformer(self._model_name)

        return self._model
