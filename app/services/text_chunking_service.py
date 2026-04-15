from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


class TextChunkingService:
    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            add_start_index=True,
        )

    def split(self, documents: list[Document]) -> list[Document]:
        non_empty_documents = [doc for doc in documents if doc.page_content.strip()]
        if not non_empty_documents:
            return []
        return self._splitter.split_documents(non_empty_documents)
