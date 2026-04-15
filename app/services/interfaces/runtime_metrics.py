from abc import ABC, abstractmethod


class IRuntimeMetrics(ABC):
    @abstractmethod
    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def increment_fallback_answers(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def increment_rate_limited_requests(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> dict:
        raise NotImplementedError
