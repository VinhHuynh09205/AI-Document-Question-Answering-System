from pathlib import Path

from langchain_core.documents import Document


class CitationBuilder:
    @staticmethod
    def build_sources(context_docs: list[Document]) -> list[str]:
        unique_sources: list[str] = []
        seen: set[str] = set()

        for doc in context_docs:
            source_ref = CitationBuilder._build_source_ref(doc)
            if source_ref in seen:
                continue

            seen.add(source_ref)
            unique_sources.append(source_ref)

        return unique_sources

    @staticmethod
    def _build_source_ref(document: Document) -> str:
        metadata = document.metadata
        raw_source = str(metadata.get("source", "unknown"))
        filename = Path(raw_source).name
        if "_" in filename and len(filename.split("_", 1)[0]) == 32:
            filename = filename.split("_", 1)[1]

        page = metadata.get("page_number") or metadata.get("page")
        slide_number = metadata.get("slide_number") or metadata.get("slide")
        slide_title = str(metadata.get("slide_title") or "").strip()
        sheet_name = str(metadata.get("sheet_name") or metadata.get("sheet") or "").strip()
        range_address = str(metadata.get("range_address") or "").strip()
        row_range = str(metadata.get("row_range") or "").strip()
        section_path = str(metadata.get("section_path") or "").strip()
        structure_path = str(metadata.get("structure_path") or "").strip()

        if page is not None:
            detail_parts = [f"trang {page}"]
            if section_path and section_path not in {"overview", f"Page: {page}"}:
                detail_parts.append(section_path)
            return f"{filename} ({', '.join(detail_parts)})"

        if slide_number is not None:
            detail_parts = [f"slide {slide_number}"]
            if slide_title and slide_title != f"Slide {slide_number}":
                detail_parts.append(slide_title)
            return f"{filename} ({', '.join(detail_parts)})"

        if sheet_name:
            detail_parts = [f"sheet {sheet_name}"]
            if range_address:
                detail_parts.append(range_address)
            elif row_range:
                detail_parts.append(f"rows {row_range}")
            return f"{filename} ({', '.join(detail_parts)})"

        if section_path and section_path not in {"overview", "paragraph"}:
            return f"{filename} ({section_path})"

        if structure_path and structure_path not in {"overview", "paragraph"}:
            return f"{filename} ({structure_path})"

        return filename