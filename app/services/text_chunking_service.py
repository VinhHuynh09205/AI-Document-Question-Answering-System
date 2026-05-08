from langchain_core.documents import Document

from app.services.chunking import ChunkingStrategyFactory


class TextChunkingService:
    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self._chunk_size = max(200, int(chunk_size))
        self._chunk_overlap = max(0, min(int(chunk_overlap), self._chunk_size // 2))
        self._strategy_factory = ChunkingStrategyFactory()

    def split(self, documents: list[Document]) -> list[Document]:
        non_empty_documents = [doc for doc in documents if doc.page_content.strip()]
        if not non_empty_documents:
            return []

        chunks: list[Document] = []
        for document in non_empty_documents:
            strategy = self._strategy_factory.resolve(document)
            chunks.extend(
                strategy.split(
                    document,
                    chunk_size=self._chunk_size,
                    chunk_overlap=self._chunk_overlap,
                )
            )
        return chunks
