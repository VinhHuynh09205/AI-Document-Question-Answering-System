from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.models.entities import AnswerResult


class IQuestionAnsweringService(ABC):
    @abstractmethod
    def ask(
        self,
        question: str,
        metadata_filter: dict[str, str] | None = None,
        top_k: int | None = None,
    ) -> AnswerResult:
        raise NotImplementedError

    def ask_stream(
        self,
        question: str,
        metadata_filter: dict[str, str] | None = None,
        top_k: int | None = None,
    ) -> Iterator[str]:
        """Yield answer tokens. Default: yield full answer at once."""
        result = self.ask(question, metadata_filter=metadata_filter, top_k=top_k)
        yield result.answer
