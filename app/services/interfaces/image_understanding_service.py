from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class ImageAnalysisResult:
    text: str
    provider: str


class IImageUnderstandingService(ABC):
    @abstractmethod
    def analyze_image(
        self,
        image_bytes: bytes,
        *,
        source: str,
        hint: str,
    ) -> ImageAnalysisResult:
        raise NotImplementedError
