from dataclasses import dataclass
import re

from langchain_core.documents import Document

from app.services.chunking import ChunkingStrategyFactory


@dataclass(frozen=True, slots=True)
class ChunkingProfile:
    name: str
    chunk_size: int
    chunk_overlap: int


class TextChunkingService:
    _TOKEN_RE = re.compile(r"[A-Za-z0-9\u00C0-\u024F\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]+")

    def __init__(
        self,
        chunk_size: int,
        chunk_overlap: int,
        chunk_profiles: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        self._chunk_size = max(200, int(chunk_size))
        self._chunk_overlap = max(0, min(int(chunk_overlap), self._chunk_size // 2))
        self._strategy_factory = ChunkingStrategyFactory()
        self._chunk_profiles = self._build_chunk_profiles(chunk_profiles or {})

    def split(self, documents: list[Document]) -> list[Document]:
        non_empty_documents = [doc for doc in documents if doc.page_content.strip()]
        if not non_empty_documents:
            return []

        chunks: list[Document] = []
        for document in non_empty_documents:
            strategy = self._strategy_factory.resolve(document)
            profile = self._resolve_profile(document)
            chunk_batch = strategy.split(
                document,
                chunk_size=profile.chunk_size,
                chunk_overlap=profile.chunk_overlap,
            )
            self._enrich_chunk_batch(chunk_batch, profile=profile, strategy_name=type(strategy).__name__)
            chunks.extend(chunk_batch)
        return chunks

    def _build_chunk_profiles(
        self,
        overrides: dict[str, tuple[int, int]],
    ) -> dict[str, ChunkingProfile]:
        profiles: dict[str, ChunkingProfile] = {}
        for name in ("paragraph", "section", "slide", "structured", "image"):
            override = overrides.get(name)
            if override is None:
                size = self._chunk_size
                overlap = self._chunk_overlap
            else:
                size = max(200, int(override[0]))
                overlap = max(0, min(int(override[1]), size // 2))
            profiles[name] = ChunkingProfile(name=name, chunk_size=size, chunk_overlap=overlap)
        return profiles

    def _resolve_profile(self, document: Document) -> ChunkingProfile:
        profile_key = self._strategy_factory.profile_key(document)
        return self._chunk_profiles.get(profile_key, self._chunk_profiles["paragraph"])

    def _enrich_chunk_batch(
        self,
        chunk_batch: list[Document],
        *,
        profile: ChunkingProfile,
        strategy_name: str,
    ) -> None:
        for chunk_position, chunk in enumerate(chunk_batch, start=1):
            chunk.metadata.setdefault("chunk_profile", profile.name)
            chunk.metadata.setdefault("chunk_strategy", strategy_name)
            chunk.metadata.setdefault("chunk_profile_size", profile.chunk_size)
            chunk.metadata.setdefault("chunk_profile_overlap", profile.chunk_overlap)
            chunk.metadata.setdefault(
                "structure_path",
                self._build_fallback_structure_path(chunk),
            )
            chunk.metadata.setdefault("citation_hint", str(chunk.metadata.get("structure_path") or ""))
            chunk.metadata["chunk_sequence_in_parent"] = chunk_position
            quality_score = self._score_chunk_quality(chunk)
            chunk.metadata["chunk_quality_score"] = quality_score
            chunk.metadata["chunk_quality_band"] = self._resolve_quality_band(quality_score)

    def _build_fallback_structure_path(self, chunk: Document) -> str:
        metadata = chunk.metadata
        parts: list[str] = []

        sheet_name = str(metadata.get("sheet_name") or metadata.get("sheet") or "").strip()
        row_range = str(metadata.get("row_range") or "").strip()
        table_name = str(metadata.get("table_name") or "").strip()
        page_number = metadata.get("page_number") or metadata.get("page")
        slide_number = metadata.get("slide_number") or metadata.get("slide")
        section_path = str(metadata.get("section_path") or "").strip()
        section_title = str(metadata.get("section_title") or "").strip()

        if sheet_name:
            parts.append(f"Sheet: {sheet_name}")
        if table_name:
            parts.append(f"Table: {table_name}")
        if row_range:
            parts.append(f"Rows: {row_range}")
        if slide_number is not None:
            parts.append(f"Slide: {slide_number}")
        if page_number is not None:
            parts.append(f"Page: {page_number}")
        if section_path:
            parts.append(section_path)
        elif section_title and section_title not in {"overview", "paragraph"}:
            parts.append(section_title)

        if not parts:
            source = str(metadata.get("source") or "document").strip()
            parts.append(source.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or "document")

        return " > ".join(parts)

    @classmethod
    def _score_chunk_quality(cls, chunk: Document) -> float:
        text = str(chunk.page_content or "").strip()
        if not text:
            return 0.0

        tokens = cls._TOKEN_RE.findall(text.casefold())
        unique_ratio = (len(set(tokens)) / len(tokens)) if tokens else 0.0
        char_score = min(1.0, len(text) / 320.0)
        token_score = min(1.0, len(tokens) / 60.0)
        diversity_score = min(1.0, unique_ratio / 0.72) if tokens else 0.0

        metadata = chunk.metadata
        structure_score = 0.0
        if str(metadata.get("structure_path") or "").strip():
            structure_score += 0.55
        if any(
            metadata.get(key) is not None
            for key in ("row_range", "page_number", "page", "slide_number", "slide", "sheet_name", "section_path")
        ):
            structure_score += 0.45
        structure_score = min(1.0, structure_score)

        weighted_score = (
            (0.35 * char_score)
            + (0.20 * token_score)
            + (0.25 * diversity_score)
            + (0.20 * structure_score)
        )
        return round(min(1.0, weighted_score), 4)

    @staticmethod
    def _resolve_quality_band(score: float) -> str:
        if score >= 0.75:
            return "high"
        if score >= 0.45:
            return "medium"
        return "low"
