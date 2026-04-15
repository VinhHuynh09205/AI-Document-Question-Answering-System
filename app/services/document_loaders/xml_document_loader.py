import xml.etree.ElementTree as ET
from pathlib import Path

from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader
from app.utils.text_io import read_text_with_fallback


class XmlDocumentLoader(IDocumentLoader):
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".xml"

    def load(self, file_path: Path) -> list[Document]:
        raw = read_text_with_fallback(file_path)
        root = ET.fromstring(raw)  # noqa: S314
        lines: list[str] = []
        self._extract_text(root, lines)
        content = "\n".join(lines)

        return [
            Document(
                page_content=content,
                metadata={"source": str(file_path), "extension": ".xml"},
            )
        ]

    def _extract_text(self, element: ET.Element, lines: list[str], depth: int = 0) -> None:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        text = (element.text or "").strip()
        if text:
            lines.append(f"{tag}: {text}")
        for child in element:
            self._extract_text(child, lines, depth + 1)
        tail = (element.tail or "").strip()
        if tail:
            lines.append(tail)
