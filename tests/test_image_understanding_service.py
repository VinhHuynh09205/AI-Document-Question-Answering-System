import io
import sys
import time
import types

import numpy as np
from PIL import Image

from app.core.config import Settings
from app.services.image_understanding_service import ImageUnderstandingService


def _patch_signal_stats(monkeypatch, service: ImageUnderstandingService) -> None:
    monkeypatch.setattr(
        service,
        "_compute_image_signal_stats",
        lambda _image_bytes: {
            "width": 640.0,
            "height": 360.0,
            "pixels": 230400.0,
            "entropy": 3.4,
            "edge_mean": 5.4,
            "edge_density": 0.08,
            "grayscale_stddev": 14.0,
            "text_density": 0.09,
        },
    )


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
    _patch_signal_stats(monkeypatch, service)
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
    _patch_signal_stats(monkeypatch, service)
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
    _patch_signal_stats(monkeypatch, service)
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
        ocr_max_variants_per_image=3,
        ocr_max_seconds_per_image=15.0,
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
    _patch_signal_stats(monkeypatch, service)

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


def test_image_understanding_low_signal_still_uses_local_ocr(monkeypatch) -> None:
    settings = Settings(
        google_api_key="",
        enable_image_understanding=True,
        enable_gemini_image_understanding=False,
        enable_local_vision_fallback=False,
        enable_local_ocr_fallback=True,
        image_understanding_min_bytes=1,
    )
    service = ImageUnderstandingService(settings=settings)

    monkeypatch.setattr(service, "_normalize_image", lambda _: (b"image-bytes", "image/png"))
    _patch_signal_stats(monkeypatch, service)
    monkeypatch.setattr(service, "_looks_like_informative_image", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(service, "_analyze_with_local_ocr", lambda _: "Chart trend 19.5 20.8 24.2")

    result = service.analyze_image(
        b"ignored",
        source="sample-low-signal.png",
        hint="docx image 2",
    )

    assert result.provider == "local_ocr"
    assert "19.5" in result.text


def test_image_understanding_low_signal_returns_reason_when_all_providers_fail(monkeypatch) -> None:
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
    _patch_signal_stats(monkeypatch, service)
    monkeypatch.setattr(service, "_looks_like_informative_image", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(service, "_analyze_with_gemini", lambda **_: "")
    monkeypatch.setattr(service, "_analyze_with_local_vision", lambda **_: "")
    monkeypatch.setattr(service, "_analyze_with_local_ocr", lambda _: "")

    result = service.analyze_image(
        b"ignored",
        source="sample-low-signal.png",
        hint="docx image 2",
    )

    assert result.provider == "image_low_signal"
    assert result.text == ""


def test_local_vision_fail_fast_when_endpoint_unreachable(monkeypatch) -> None:
    settings = Settings(
        google_api_key="",
        enable_image_understanding=True,
        enable_gemini_image_understanding=False,
        enable_local_vision_fallback=True,
        enable_local_ocr_fallback=False,
        image_understanding_min_bytes=1,
    )
    service = ImageUnderstandingService(settings=settings)

    monkeypatch.setattr(service, "_has_reachable_local_vision_endpoint", lambda: False)

    calls = {"resolve_models": 0}

    def _track_resolve_models() -> list[str]:
        calls["resolve_models"] += 1
        return ["llava:7b"]

    monkeypatch.setattr(service, "_resolve_local_vision_models", _track_resolve_models)

    result = service._analyze_with_local_vision(
        image_bytes=b"image-bytes",
        source="sample.png",
        hint="docx image",
    )

    assert result == ""
    assert calls["resolve_models"] == 0
    assert service._is_provider_in_backoff("local_vision")


def test_image_understanding_skips_low_information_images_before_provider_chain(monkeypatch) -> None:
    settings = Settings(
        google_api_key="dummy-key",
        enable_image_understanding=True,
        enable_gemini_image_understanding=True,
        enable_local_vision_fallback=True,
        enable_local_ocr_fallback=True,
        image_understanding_min_bytes=1,
    )
    service = ImageUnderstandingService(settings=settings)

    provider_calls = {"gemini": 0, "local_vision": 0, "local_ocr": 0}

    monkeypatch.setattr(service, "_normalize_image", lambda _: (b"image-bytes", "image/png"))
    monkeypatch.setattr(
        service,
        "_compute_image_signal_stats",
        lambda _image_bytes: {
            "width": 128.0,
            "height": 96.0,
            "pixels": 12288.0,
            "entropy": 1.4,
            "edge_mean": 1.2,
            "edge_density": 0.002,
            "grayscale_stddev": 2.1,
            "text_density": 0.003,
        },
    )

    def _fake_gemini(**_kwargs):
        provider_calls["gemini"] += 1
        return "unexpected"

    def _fake_local_vision(**_kwargs):
        provider_calls["local_vision"] += 1
        return "unexpected"

    def _fake_local_ocr(_image_bytes):
        provider_calls["local_ocr"] += 1
        return "unexpected"

    monkeypatch.setattr(service, "_analyze_with_gemini", _fake_gemini)
    monkeypatch.setattr(service, "_analyze_with_local_vision", _fake_local_vision)
    monkeypatch.setattr(service, "_analyze_with_local_ocr", _fake_local_ocr)

    result = service.analyze_image(
        b"ignored",
        source="logo.png",
        hint="decorative asset",
    )

    assert result.provider == "image_low_information"
    assert result.text == ""
    assert provider_calls["gemini"] == 0
    assert provider_calls["local_vision"] == 0
    assert provider_calls["local_ocr"] == 0


def test_local_ocr_respects_variant_limit(monkeypatch) -> None:
    settings = Settings(
        google_api_key="",
        enable_image_understanding=True,
        enable_local_ocr_fallback=True,
        image_ocr_min_confidence=0.4,
        ocr_max_variants_per_image=1,
        ocr_max_seconds_per_image=15.0,
    )
    service = ImageUnderstandingService(settings=settings)

    class FakeRapidOCR:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, _image_array):
            self.calls += 1
            return [([0, 0, 1, 1], "Important line", 0.92)], None

    fake_ocr_engine = FakeRapidOCR()
    fake_module = types.SimpleNamespace(RapidOCR=lambda: fake_ocr_engine)
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", fake_module)
    monkeypatch.setattr(service, "_build_ocr_image_variants", lambda *_: ["v1", "v2", "v3"])

    image = Image.new("RGB", (320, 160), color="white")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")

    text = service._analyze_with_local_ocr(image_bytes.getvalue())

    assert fake_ocr_engine.calls == 1
    assert "Important line" in text
