from abc import ABC, abstractmethod
from pathlib import Path

from langchain_core.documents import Document


class IDocumentLoader(ABC):
    @abstractmethod
    def supports(self, file_extension: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def load(self, file_path: Path) -> list[Document]:
        raise NotImplementedError
