from app.models.entities import AnswerResult
from app.services.interfaces.question_answering_service import IQuestionAnsweringService
from app.services.qa_constants import FALLBACK_ANSWER


class StubQuestionAnsweringService(IQuestionAnsweringService):
    def ask(
        self,
        question: str,
        metadata_filter: dict[str, str] | None = None,
        top_k: int | None = None,
    ) -> AnswerResult:
        return AnswerResult(
            answer=FALLBACK_ANSWER,
            sources=[],
            context_found=False,
        )
