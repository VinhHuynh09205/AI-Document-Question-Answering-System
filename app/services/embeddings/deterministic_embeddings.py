import hashlib

from langchain_core.embeddings import Embeddings


class DeterministicEmbeddings(Embeddings):
    def __init__(self, dimension: int = 256) -> None:
        self._dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        seed = text.encode("utf-8")
        values: list[float] = []
        counter = 0

        while len(values) < self._dimension:
            digest = hashlib.sha256(seed + str(counter).encode("ascii")).digest()
            for byte in digest:
                values.append(byte / 255.0)
                if len(values) == self._dimension:
                    break
            counter += 1

        return values
