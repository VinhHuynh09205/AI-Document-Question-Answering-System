from pathlib import Path

from bs4 import BeautifulSoup
from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader
from app.utils.text_io import read_text_with_fallback


class HtmlDocumentLoader(IDocumentLoader):
    _REMOVE_TAGS = {"script", "style", "nav", "footer", "header", "noscript"}

    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() in (".html", ".htm")

    def load(self, file_path: Path) -> list[Document]:
        raw = read_text_with_fallback(file_path)
        soup = BeautifulSoup(raw, "html.parser")

        for tag in soup.find_all(self._REMOVE_TAGS):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        return [
            Document(
                page_content=text,
                metadata={
                    "source": str(file_path),
                    "extension": file_path.suffix.lower(),
                },
            )
        ]
