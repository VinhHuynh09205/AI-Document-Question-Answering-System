from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Sequence

from langchain_core.documents import Document


class ILLMProvider(ABC):
    @abstractmethod
    def generate_grounded_answer(self, question: str, context_docs: Sequence[Document]) -> str:
        raise NotImplementedError

    def stream_grounded_answer(self, question: str, context_docs: Sequence[Document]) -> Iterator[str]:
        """Yield answer token-by-token. Default fallback: yield full answer at once."""
        yield self.generate_grounded_answer(question, context_docs)
