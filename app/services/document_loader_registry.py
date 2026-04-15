from pathlib import Path

from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader


class DocumentLoaderRegistry:
    def __init__(self, loaders: list[IDocumentLoader]) -> None:
        self._loaders = loaders

    def load_file(self, file_path: Path) -> list[Document]:
        extension = file_path.suffix.lower()
        loader = self._resolve_loader(extension)
        if loader is None:
            raise ValueError(f"No loader configured for file type: {extension}")
        return loader.load(file_path)

    def _resolve_loader(self, extension: str) -> IDocumentLoader | None:
        for loader in self._loaders:
            if loader.supports(extension):
                return loader
        return None
