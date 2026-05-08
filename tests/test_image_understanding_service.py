import io
import sys
import time
import types

import numpy as np
from PIL import Image

from app.core.config import Settings
from app.services.image_understanding_service import ImageUnderstandingService


def test_image_understanding_prefers_gemini_then_stops(monkeypatch) -> None:
    settings = Settings(
        google_api_key="dummy-key",
        enable_image_understanding=True,
        enable_gemini_image_understanding=True,
        enable_local_vision_fallback=True,
        enable_local_ocr_fallback=True,
        image_understanding_min_bytes=1,
    )
    service = ImageUnderstandingService(settings=settings)

    monkeypatch.setattr(service, "_normalize_image", lambda _: (b"image-bytes", "image/png"))
    monkeypatch.setattr(
        service,
        "_analyze_with_gemini",
        lambda **_: "Detected chart with trend and labels.",
    )

    result = service.analyze_image(
        b"ignored",
        source="sample.pdf",
        hint="pdf page 1 image 1",
    )

    assert result.provider == "gemini"
    assert "trend" in result.text


def test_image_understanding_falls_back_to_local_vision(monkeypatch) -> None:
    settings = Settings(
        google_api_key="dummy-key",
        enable_image_understanding=True,
        enable_gemini_image_understanding=True,
        enable_local_vision_fallback=True,
        enable_local_ocr_fallback=True,
        image_understanding_min_bytes=1,
    )
    service = ImageUnderstandingService(settings=settings)

    monkeypatch.setattr(service, "_normalize_image", lambda _: (b"image-bytes", "image/png"))
    monkeypatch.setattr(service, "_analyze_with_gemini", lambda **_: "")
    monkeypatch.setattr(
        service,
        "_analyze_with_local_vision",
        lambda **_: "Local vision summary for process diagram.",
    )

    result = service.analyze_image(
        b"ignored",
        source="sample.pptx",
        hint="slide 2 image 1",
    )

    assert result.provider == "local_vision"
    assert "process diagram" in result.text


def test_image_understanding_falls_back_to_local_ocr(monkeypatch) -> None:
    settings = Settings(
        google_api_key="",
        enable_image_understanding=True,
        enable_gemini_image_understanding=True,
        enable_local_vision_fallback=True,
        enable_local_ocr_fallback=True,
        image_understanding_min_bytes=1,
    )
    service = ImageUnderstandingService(settings=settings)

    monkeypatch.setattr(service, "_normalize_image", lambda _: (b"image-bytes", "image/png"))
    monkeypatch.setattr(service, "_analyze_with_local_vision", lambda **_: "")
    monkeypatch.setattr(
        service,
        "_analyze_with_local_ocr",
        lambda _: "OCR extracted invoice number 12345",
    )

    result = service.analyze_image(
        b"ignored",
        source="sample.docx",
        hint="docx image 2",
    )

    assert result.provider == "local_ocr"
    assert "invoice" in result.text


def test_local_ocr_uses_variants_and_relaxed_threshold(monkeypatch) -> None:
    settings = Settings(
        google_api_key="",
        enable_image_understanding=True,
        enable_local_ocr_fallback=True,
        image_ocr_min_confidence=0.60,
    )
    service = ImageUnderstandingService(settings=settings)

    class FakeRapidOCR:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, _image_array):
            self.calls += 1
            if self.calls == 1:
                return [
                    ([0, 0, 1, 1], "Revenue Q1 120", 0.55),
                    ([0, 0, 1, 1], "Trend up", 0.58),
                ], None
            if self.calls == 2:
                return [
                    ([0, 0, 1, 1], "Trend up", 0.81),
                ], None
            return [], None

    fake_ocr_engine = FakeRapidOCR()
    fake_module = types.SimpleNamespace(RapidOCR=lambda: fake_ocr_engine)
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", fake_module)

    monkeypatch.setattr(
        service,
        "_build_ocr_image_variants",
        lambda *_: ["v1", "v2", "v3"],
    )

    image = Image.new("RGB", (256, 128), color="white")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")

    text = service._analyze_with_local_ocr(image_bytes.getvalue())

    assert fake_ocr_engine.calls == 3
    assert "Trend up" in text
    assert "Revenue Q1 120" in text


def test_build_ocr_image_variants_returns_three_rgb_arrays() -> None:
    settings = Settings()
    service = ImageUnderstandingService(settings=settings)

    image = Image.new("RGB", (128, 64), color="white")

    variants = service._build_ocr_image_variants(image, np)

    assert len(variants) == 3
    for variant in variants:
        assert len(variant.shape) == 3
        assert variant.shape[2] == 3


def test_image_understanding_skips_backoff_providers(monkeypatch) -> None:
    settings = Settings(
        google_api_key="dummy-key",
        enable_image_understanding=True,
        enable_gemini_image_understanding=True,
        enable_local_vision_fallback=True,
        enable_local_ocr_fallback=True,
        image_understanding_min_bytes=1,
    )
    service = ImageUnderstandingService(settings=settings)

    calls = {"gemini": 0, "local_vision": 0}

    monkeypatch.setattr(service, "_normalize_image", lambda _: (b"image-bytes", "image/png"))

    def _fake_gemini(**_kwargs):
        calls["gemini"] += 1
        return "gemini"

    def _fake_local_vision(**_kwargs):
        calls["local_vision"] += 1
        return "local"

    monkeypatch.setattr(service, "_analyze_with_gemini", _fake_gemini)
    monkeypatch.setattr(service, "_analyze_with_local_vision", _fake_local_vision)
    monkeypatch.setattr(service, "_analyze_with_local_ocr", lambda _img: "OCR fallback")

    future = time.monotonic() + 120
    service._gemini_backoff_until = future
    service._local_vision_backoff_until = future

    result = service.analyze_image(
        b"ignored",
        source="sample.docx",
        hint="docx image 1",
    )

    assert result.provider == "local_ocr"
    assert "OCR" in result.text
    assert calls["gemini"] == 0
    assert calls["local_vision"] == 0
