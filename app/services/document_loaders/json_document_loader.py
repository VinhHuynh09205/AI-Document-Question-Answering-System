import json
from pathlib import Path

from langchain_core.documents import Document

from app.services.interfaces.document_loader import IDocumentLoader
from app.utils.text_io import read_text_with_fallback


class JsonDocumentLoader(IDocumentLoader):
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == ".json"

    def load(self, file_path: Path) -> list[Document]:
        raw = read_text_with_fallback(file_path)
        data = json.loads(raw)
        content = self._flatten(data)

        return [
            Document(
                page_content=content,
                metadata={"source": str(file_path), "extension": ".json"},
            )
        ]

    def _flatten(self, obj: object, prefix: str = "") -> str:
        lines: list[str] = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                lines.append(self._flatten(value, new_prefix))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                lines.append(self._flatten(item, f"{prefix}[{i}]"))
        else:
            lines.append(f"{prefix}: {obj}")
        return "\n".join(line for line in lines if line.strip())
