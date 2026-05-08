from pathlib import Path

from bs4 import BeautifulSoup
from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader
from app.utils.text_io import read_text_with_fallback


class HtmlDocumentLoader(IDocumentLoader):
    _REMOVE_TAGS = {"script", "style", "nav", "footer", "header", "noscript", "aside"}
    _SEMANTIC_BLOCK_TAGS = {
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "li", "article", "section", "main",
        "th", "td", "caption", "pre", "code",
    }

    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() in (".html", ".htm")

    def load(self, file_path: Path) -> list[Document]:
        raw = read_text_with_fallback(file_path)
        soup = BeautifulSoup(raw, "html.parser")

        for tag in soup.find_all(self._REMOVE_TAGS):
            tag.decompose()

        for tag in soup.find_all(attrs={"hidden": True}):
            tag.decompose()

        for tag in soup.find_all(attrs={"aria-hidden": "true"}):
            tag.decompose()

        for tag in soup.select("[style*='display:none'], [style*='display: none']"):
            tag.decompose()

        lines: list[str] = []
        seen: set[str] = set()

        for tag in soup.find_all(self._SEMANTIC_BLOCK_TAGS):
            text = tag.get_text(separator=" ", strip=True)
            if not text:
                continue

            if tag.name.startswith("h") and len(tag.name) == 2 and tag.name[1].isdigit():
                level = int(tag.name[1])
                text = f"{'#' * level} {text}"
            elif tag.name == "li":
                text = f"- {text}"

            if text in seen:
                continue
            seen.add(text)
            lines.append(text)

        text = "\n".join(lines).strip()
        if not text:
            text = soup.get_text(separator="\n", strip=True)

        return [
            Document(
                page_content=text,
                metadata={
                    "source": str(file_path),
                    "extension": file_path.suffix.lower(),
                    "content_type": "html_semantic",
                },
            )
        ]
