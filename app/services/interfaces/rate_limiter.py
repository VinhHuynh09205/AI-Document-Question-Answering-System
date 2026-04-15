from abc import ABC, abstractmethod


class IRateLimiter(ABC):
    @abstractmethod
    def consume(self, bucket: str, key: str) -> tuple[bool, int]:
        raise NotImplementedError
