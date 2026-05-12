import base64
import logging
import re
import time
from io import BytesIO
from pathlib import Path
from threading import BoundedSemaphore

import httpx
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from app.core.config import Settings
from app.services.interfaces.image_understanding_service import (
    IImageUnderstandingService,
    ImageAnalysisResult,
)


logger = logging.getLogger(__name__)

_PROVIDER_BACKOFF_SECONDS = 300.0

_IMAGE_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}

_DEFAULT_IMAGE_ANALYSIS_PROMPT = (
    "Analyze this document image and extract useful knowledge for retrieval. "
    "Return concise plain text in this order: "
    "(1) visible text, "
    "(2) visual structure and relationships, "
    "(3) numeric/chart/table observations, "
    "(4) key conclusions. "
    "Do not use markdown code blocks."
)

_ANALYSIS_NOISE_RE = re.compile(
    r"(local_ocr|local_vision|provider[:=]|image\s*analysis|slide\s*image)",
    re.IGNORECASE,
)
_MEANINGFUL_CHAR_RE = re.compile(r"[A-Za-z\u00C0-\u024F\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]")
_SYMBOL_ONLY_RE = re.compile(r"^[^A-Za-z\u00C0-\u024F\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF0-9]+$")
_DEFAULT_LOCAL_VISION_MODEL_CANDIDATES = (
    "qwen2.5vl:7b",
    "llava:13b",
    "llava:7b",
)


class ImageUnderstandingService(IImageUnderstandingService):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rapid_ocr_engine = None
        self._image_analysis_semaphore = BoundedSemaphore(
            max(1, int(settings.image_analysis_max_concurrency))
        )
        self._local_vision_semaphore = BoundedSemaphore(
            max(1, int(settings.local_vision_max_concurrency))
        )
        self._local_ocr_semaphore = BoundedSemaphore(
            max(1, int(settings.local_ocr_max_concurrency))
        )
        self._gemini_backoff_until = 0.0
        self._local_vision_backoff_until = 0.0
        self._local_vision_model_cache: tuple[str, ...] | None = None
        self._local_vision_models_cached_at = 0.0
        self._local_vision_endpoint_available: bool | None = None
        self._local_vision_endpoint_checked_at = 0.0

    def analyze_image(
        self,
        image_bytes: bytes,
        *,
        source: str,
        hint: str,
    ) -> ImageAnalysisResult:
        if not self._settings.enable_image_understanding:
            return ImageAnalysisResult(text="", provider="disabled")

        normalized_bytes, mime_type = self._normalize_image(image_bytes)
        if not normalized_bytes:
            return ImageAnalysisResult(text="", provider="invalid_image")

        if len(normalized_bytes) < self._settings.image_understanding_min_bytes:
            return ImageAnalysisResult(text="", provider="image_too_small")

        signal_stats = self._compute_image_signal_stats(normalized_bytes)
        if signal_stats is None:
            return ImageAnalysisResult(text="", provider="invalid_image")
        if self._should_skip_low_information_image(signal_stats):
            return ImageAnalysisResult(text="", provider="image_low_information")

        self._image_analysis_semaphore.acquire()
        try:
            low_signal_image = not self._looks_like_informative_image(
                normalized_bytes,
                signal_stats=signal_stats,
            )
            if low_signal_image:
                logger.info("image_preflight_low_signal source=%s hint=%s", source, hint)

            if (
                self._settings.enable_gemini_image_understanding
                and self._settings.google_api_key
                and not self._is_provider_in_backoff("gemini")
            ):
                gemini_text = self._analyze_with_gemini(
                    image_bytes=normalized_bytes,
                    mime_type=mime_type,
                    source=source,
                    hint=hint,
                )
                cleaned_gemini_text = self._clean_analysis_text(gemini_text)
                if cleaned_gemini_text:
                    return ImageAnalysisResult(text=cleaned_gemini_text, provider="gemini")

            if (
                self._settings.enable_local_vision_fallback
                and not self._is_provider_in_backoff("local_vision")
            ):
                local_vision_text = self._analyze_with_local_vision(
                    image_bytes=normalized_bytes,
                    source=source,
                    hint=hint,
                )
                cleaned_local_vision_text = self._clean_analysis_text(local_vision_text)
                if cleaned_local_vision_text:
                    return ImageAnalysisResult(text=cleaned_local_vision_text, provider="local_vision")

            if self._settings.enable_local_ocr_fallback:
                local_ocr_text = self._analyze_with_local_ocr(normalized_bytes)
                cleaned_local_ocr_text = self._clean_analysis_text(local_ocr_text)
                if cleaned_local_ocr_text:
                    return ImageAnalysisResult(text=cleaned_local_ocr_text, provider="local_ocr")

            if low_signal_image:
                return ImageAnalysisResult(text="", provider="image_low_signal")

            return ImageAnalysisResult(text="", provider="no_result")
        finally:
            self._image_analysis_semaphore.release()

    def _normalize_image(self, image_bytes: bytes) -> tuple[bytes, str]:
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                width, height = image.size
                if (
                    min(width, height) < self._settings.image_understanding_min_edge_pixels
                    or max(width, height) < self._settings.image_understanding_min_edge_pixels
                ):
                    return b"", ""

                image_format = str(image.format or "PNG").upper()
                mime_type = _IMAGE_MIME_BY_FORMAT.get(image_format, "image/png")
                normalized_image = image
                image_updated = False

                if normalized_image.mode != "RGB":
                    normalized_image = normalized_image.convert("RGB")
                    image_updated = True

                max_pixels = max(10000, int(self._settings.image_analysis_max_pixels))
                pixel_count = width * height
                if pixel_count > max_pixels:
                    scale = (max_pixels / float(pixel_count)) ** 0.5
                    new_size = (
                        max(1, int(round(width * scale))),
                        max(1, int(round(height * scale))),
                    )
                    normalized_image = normalized_image.resize(new_size, Image.Resampling.BILINEAR)
                    image_updated = True

                if not image_updated and image_format in _IMAGE_MIME_BY_FORMAT and normalized_image.mode == "RGB":
                    return image_bytes, mime_type

                buffer = BytesIO()
                normalized_image.save(buffer, format="PNG")
                return buffer.getvalue(), "image/png"
        except (UnidentifiedImageError, OSError):
            return b"", ""

    def _compute_image_signal_stats(self, image_bytes: bytes) -> dict[str, float] | None:
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                grayscale = ImageOps.grayscale(image)
                width, height = grayscale.size
                pixels = max(1, width * height)

                grayscale_stats = ImageStat.Stat(grayscale)
                grayscale_stddev = float(grayscale_stats.stddev[0])
                entropy = float(grayscale.entropy())

                edges = grayscale.filter(ImageFilter.FIND_EDGES)
                edge_stats = ImageStat.Stat(edges)
                edge_mean = float(edge_stats.mean[0])
                edge_histogram = edges.histogram()
                edge_density = float(sum(edge_histogram[36:])) / float(pixels)

                text_density = self._estimate_text_density(grayscale)

                return {
                    "width": float(width),
                    "height": float(height),
                    "pixels": float(pixels),
                    "entropy": entropy,
                    "edge_mean": edge_mean,
                    "edge_density": edge_density,
                    "grayscale_stddev": grayscale_stddev,
                    "text_density": text_density,
                }
        except Exception:
            return None

    @staticmethod
    def _estimate_text_density(grayscale: Image.Image) -> float:
        preview = grayscale
        max_edge = max(preview.size)
        if max_edge > 384:
            scale = 384 / float(max_edge)
            new_size = (
                max(1, int(round(preview.size[0] * scale))),
                max(1, int(round(preview.size[1] * scale))),
            )
            preview = preview.resize(new_size, Image.Resampling.BILINEAR)

        histogram = preview.histogram()
        total = max(1, sum(histogram))
        dark_ratio = float(sum(histogram[:96])) / float(total)
        mid_ratio = float(sum(histogram[96:176])) / float(total)

        edges = preview.filter(ImageFilter.FIND_EDGES)
        edge_histogram = edges.histogram()
        edge_ratio = float(sum(edge_histogram[32:])) / float(total)

        return min(1.0, (dark_ratio * 0.55) + (mid_ratio * 0.2) + (edge_ratio * 3.0))

    def _should_skip_low_information_image(self, signal_stats: dict[str, float]) -> bool:
        min_area = max(1, int(self._settings.image_analysis_min_area_pixels))
        min_entropy = max(0.0, float(self._settings.image_analysis_min_entropy))
        min_text_density = max(0.0, float(self._settings.image_analysis_min_text_density))
        min_grayscale_std = max(0.0, float(self._settings.image_analysis_min_grayscale_stddev))

        if signal_stats.get("pixels", 0.0) < float(min_area):
            return True

        entropy = signal_stats.get("entropy", 0.0)
        text_density = signal_stats.get("text_density", 0.0)
        edge_density = signal_stats.get("edge_density", 0.0)
        grayscale_stddev = signal_stats.get("grayscale_stddev", 0.0)

        if entropy < min_entropy and text_density < min_text_density:
            return True

        if edge_density < (min_text_density * 0.5) and grayscale_stddev < (min_grayscale_std * 0.75):
            return True

        return False

    def _looks_like_informative_image(
        self,
        image_bytes: bytes,
        *,
        signal_stats: dict[str, float] | None = None,
    ) -> bool:
        min_edge_mean = float(self._settings.image_analysis_min_edge_mean)
        min_grayscale_std = float(self._settings.image_analysis_min_grayscale_stddev)
        min_text_density = max(0.0, float(self._settings.image_analysis_min_text_density))

        if min_edge_mean <= 0 and min_grayscale_std <= 0 and min_text_density <= 0:
            return True

        stats = signal_stats or self._compute_image_signal_stats(image_bytes)
        if stats is None:
            return True

        edge_mean = stats.get("edge_mean", 0.0)
        grayscale_stddev = stats.get("grayscale_stddev", 0.0)
        text_density = stats.get("text_density", 0.0)
        edge_density = stats.get("edge_density", 0.0)

        if min_edge_mean > 0 and min_grayscale_std > 0:
            if edge_mean < min_edge_mean and grayscale_stddev < min_grayscale_std:
                return False
        elif min_edge_mean > 0 and edge_mean < min_edge_mean:
            return False
        elif min_grayscale_std > 0 and grayscale_stddev < min_grayscale_std:
            return False

        if min_text_density > 0 and text_density < min_text_density and edge_density < (min_text_density * 0.5):
            return False

        return True

    def _analyze_with_gemini(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        source: str,
        hint: str,
    ) -> str:
        api_key = self._settings.google_api_key.strip()
        if not api_key:
            return ""

        model = self._settings.gemini_vision_model.strip() or self._settings.gemini_model.strip()
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )

        prompt = self._build_prompt(source=source, hint=hint)
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "topP": 0.8,
                "topK": 32,
                "maxOutputTokens": 700,
            },
        }

        try:
            with httpx.Client(timeout=self._settings.image_analysis_timeout_seconds) as client:
                response = client.post(endpoint, json=payload)
        except Exception as exc:
            logger.warning(
                "gemini_image_understanding_request_failed source=%s error_type=%s",
                source,
                type(exc).__name__,
            )
            self._enter_provider_backoff("gemini", f"request_error:{type(exc).__name__}")
            return ""

        if response.status_code >= 400:
            logger.warning(
                "gemini_image_understanding_http_error source=%s status=%s",
                source,
                response.status_code,
            )
            self._enter_provider_backoff("gemini", f"http_{response.status_code}")
            return ""

        try:
            data = response.json()
        except ValueError:
            logger.warning("gemini_image_understanding_invalid_json source=%s", source)
            return ""

        return self._extract_text_from_gemini_response(data)

    def _analyze_with_local_vision(
        self,
        *,
        image_bytes: bytes,
        source: str,
        hint: str,
    ) -> str:
        self._local_vision_semaphore.acquire()
        try:
            if not self._has_reachable_local_vision_endpoint():
                self._enter_provider_backoff("local_vision", "endpoint_unreachable")
                return ""

            models = self._resolve_local_vision_models()
            max_model_attempts = max(1, int(self._settings.local_vision_max_model_attempts))
            models = models[:max_model_attempts]
            if not models:
                return ""

            endpoints = self._build_local_vision_endpoints()
            if not endpoints:
                return ""

            attempted_calls = 0
            connectivity_failures = 0
            request_timeout = max(
                1.0,
                min(
                    float(self._settings.image_analysis_timeout_seconds),
                    float(self._settings.local_vision_request_timeout_seconds),
                ),
            )

            for model in models:
                payload = {
                    "model": model,
                    "prompt": self._build_prompt(source=source, hint=hint),
                    "stream": False,
                    "images": [base64.b64encode(image_bytes).decode("ascii")],
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 600,
                    },
                }

                for endpoint in endpoints:
                    attempted_calls += 1

                    try:
                        with httpx.Client(timeout=request_timeout) as client:
                            response = client.post(endpoint, json=payload)
                    except Exception as exc:
                        logger.warning(
                            "local_vision_understanding_request_failed source=%s endpoint=%s model=%s error_type=%s",
                            source,
                            endpoint,
                            model,
                            type(exc).__name__,
                        )
                        connectivity_failures += 1
                        continue

                    if response.status_code >= 500:
                        logger.warning(
                            "local_vision_understanding_http_server_error source=%s endpoint=%s model=%s status=%s",
                            source,
                            endpoint,
                            model,
                            response.status_code,
                        )
                        connectivity_failures += 1
                        continue

                    if response.status_code >= 400:
                        if self._is_model_not_found_response(response):
                            logger.info(
                                "local_vision_model_not_found source=%s endpoint=%s model=%s",
                                source,
                                endpoint,
                                model,
                            )
                        else:
                            logger.warning(
                                "local_vision_understanding_http_error source=%s endpoint=%s model=%s status=%s",
                                source,
                                endpoint,
                                model,
                                response.status_code,
                            )
                        continue

                    try:
                        data = response.json()
                    except ValueError:
                        logger.warning(
                            "local_vision_understanding_invalid_json source=%s endpoint=%s model=%s",
                            source,
                            endpoint,
                            model,
                        )
                        continue

                    text = self._extract_local_vision_text(data)
                    normalized = self._normalize_extracted_text(text)
                    if normalized:
                        return normalized

            if attempted_calls > 0 and connectivity_failures == attempted_calls:
                self._enter_provider_backoff("local_vision", "endpoint_unreachable")

            return ""
        finally:
            self._local_vision_semaphore.release()

    def _is_provider_in_backoff(self, provider: str) -> bool:
        now = time.monotonic()
        if provider == "gemini":
            return now < self._gemini_backoff_until
        if provider == "local_vision":
            return now < self._local_vision_backoff_until
        return False

    def _enter_provider_backoff(self, provider: str, reason: str) -> None:
        now = time.monotonic()
        target_until = now + _PROVIDER_BACKOFF_SECONDS

        if provider == "gemini":
            if target_until <= self._gemini_backoff_until:
                return
            self._gemini_backoff_until = target_until
        elif provider == "local_vision":
            if target_until <= self._local_vision_backoff_until:
                return
            self._local_vision_backoff_until = target_until
        else:
            return

        logger.info(
            "image_provider_backoff_enabled provider=%s seconds=%s reason=%s",
            provider,
            int(_PROVIDER_BACKOFF_SECONDS),
            reason,
        )

    def _build_local_vision_endpoints(self) -> list[str]:
        return [endpoint + "/api/generate" for endpoint in self._build_local_vision_base_endpoints()]

    def _build_local_vision_base_endpoints(self) -> list[str]:
        base_endpoint = str(self._settings.local_vision_endpoint or "").strip().rstrip("/")
        if not base_endpoint:
            return []

        endpoints: list[str] = [base_endpoint]
        if self._is_running_in_docker() and self._is_loopback_endpoint(base_endpoint):
            if "localhost" in base_endpoint:
                endpoints.append(base_endpoint.replace("localhost", "host.docker.internal", 1))
            elif "127.0.0.1" in base_endpoint:
                endpoints.append(base_endpoint.replace("127.0.0.1", "host.docker.internal", 1))

        seen: set[str] = set()
        resolved: list[str] = []
        for endpoint in endpoints:
            if endpoint in seen:
                continue
            seen.add(endpoint)
            resolved.append(endpoint)

        return resolved

    def _resolve_local_vision_models(self) -> list[str]:
        now = time.monotonic()
        ttl_seconds = max(30, int(self._settings.local_vision_model_discovery_ttl_seconds))
        if (
            self._local_vision_model_cache is not None
            and (now - self._local_vision_models_cached_at) < ttl_seconds
        ):
            return list(self._local_vision_model_cache)

        candidates = self._get_local_vision_candidates()
        if not candidates:
            self._local_vision_model_cache = tuple()
            self._local_vision_models_cached_at = now
            return []

        installed_models = self._fetch_installed_local_vision_models()
        if installed_models:
            resolved_models: list[str] = []
            for candidate in candidates:
                installed_name = self._pick_installed_model_name(candidate, installed_models)
                if not installed_name:
                    continue
                if installed_name in resolved_models:
                    continue
                resolved_models.append(installed_name)

            if resolved_models:
                self._local_vision_model_cache = tuple(resolved_models)
                self._local_vision_models_cached_at = now
                return resolved_models

        self._local_vision_model_cache = tuple(candidates)
        self._local_vision_models_cached_at = now
        return candidates

    def _get_local_vision_candidates(self) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def _append_model_name(raw_value: str) -> None:
            model_name = str(raw_value or "").strip()
            if not model_name:
                return

            key = model_name.casefold()
            if key in seen:
                return
            seen.add(key)
            candidates.append(model_name)

        _append_model_name(self._settings.local_vision_model)
        for token in str(self._settings.local_vision_model_candidates or "").split(","):
            _append_model_name(token)
        for model_name in _DEFAULT_LOCAL_VISION_MODEL_CANDIDATES:
            _append_model_name(model_name)

        return candidates

    def _fetch_installed_local_vision_models(self) -> list[str]:
        endpoints = self._build_local_vision_base_endpoints()
        if not endpoints:
            return []

        timeout_seconds = min(3.0, float(self._settings.image_analysis_timeout_seconds))

        for endpoint in endpoints:
            tags_url = endpoint + "/api/tags"
            try:
                with httpx.Client(timeout=timeout_seconds) as client:
                    response = client.get(tags_url)
            except Exception:
                continue

            if response.status_code >= 400:
                continue

            try:
                payload = response.json()
            except ValueError:
                continue

            installed: list[str] = []
            for item in payload.get("models") or []:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                if name in installed:
                    continue
                installed.append(name)

            if installed:
                return installed

        return []

    def _has_reachable_local_vision_endpoint(self) -> bool:
        now = time.monotonic()
        ttl_seconds = max(30, int(self._settings.local_vision_model_discovery_ttl_seconds))
        if (
            self._local_vision_endpoint_available is not None
            and (now - self._local_vision_endpoint_checked_at) < ttl_seconds
        ):
            return self._local_vision_endpoint_available

        endpoints = self._build_local_vision_base_endpoints()
        if not endpoints:
            self._local_vision_endpoint_available = False
            self._local_vision_endpoint_checked_at = now
            return False

        timeout_seconds = min(2.5, float(self._settings.image_analysis_timeout_seconds))
        reachable = False

        for endpoint in endpoints:
            tags_url = endpoint + "/api/tags"
            try:
                with httpx.Client(timeout=timeout_seconds) as client:
                    response = client.get(tags_url)
            except Exception:
                continue

            if response.status_code < 500:
                reachable = True
                break

        self._local_vision_endpoint_available = reachable
        self._local_vision_endpoint_checked_at = now
        return reachable

    @staticmethod
    def _pick_installed_model_name(candidate: str, installed_models: list[str]) -> str:
        normalized_candidate = str(candidate or "").strip().casefold()
        if not normalized_candidate:
            return ""

        for installed_name in installed_models:
            if installed_name.strip().casefold() == normalized_candidate:
                return installed_name

        candidate_base = normalized_candidate.split(":", 1)[0]
        for installed_name in installed_models:
            installed_base = installed_name.strip().casefold().split(":", 1)[0]
            if installed_base == candidate_base:
                return installed_name

        return ""

    @staticmethod
    def _extract_local_vision_text(payload: dict) -> str:
        if not isinstance(payload, dict):
            return ""

        direct_text = str(payload.get("response") or "").strip()
        if direct_text:
            return direct_text

        message = payload.get("message")
        if isinstance(message, dict):
            message_text = str(message.get("content") or "").strip()
            if message_text:
                return message_text

        return str(payload.get("output") or "").strip()

    @staticmethod
    def _is_model_not_found_response(response: httpx.Response) -> bool:
        body = str(response.text or "").casefold()
        if "model" not in body:
            return False
        return (
            "not found" in body
            or "no such model" in body
            or "pull" in body
        )

    @staticmethod
    def _is_loopback_endpoint(endpoint: str) -> bool:
        normalized = str(endpoint or "").lower()
        return "localhost" in normalized or "127.0.0.1" in normalized

    @staticmethod
    def _is_running_in_docker() -> bool:
        return Path("/.dockerenv").exists()

    def _analyze_with_local_ocr(self, image_bytes: bytes) -> str:
        try:
            from rapidocr_onnxruntime import RapidOCR
            import numpy as np
        except Exception as exc:
            logger.warning(
                "rapidocr_not_available_for_local_fallback error_type=%s",
                type(exc).__name__,
            )
            return ""

        self._local_ocr_semaphore.acquire()
        try:
            if self._rapid_ocr_engine is None:
                try:
                    self._rapid_ocr_engine = RapidOCR()
                except Exception:
                    logger.exception("rapidocr_engine_init_failed")
                    return ""

            try:
                with Image.open(BytesIO(image_bytes)) as image:
                    variants = self._build_ocr_image_variants(image, np)
            except Exception:
                logger.exception("rapidocr_image_analysis_failed")
                return ""

            max_variants = max(1, int(self._settings.ocr_max_variants_per_image))
            variants = variants[:max_variants]
            deadline = time.perf_counter() + max(0.5, float(self._settings.ocr_max_seconds_per_image))

            line_scores: dict[str, float] = {}
            ordered_lines: list[str] = []
            min_confidence = float(self._settings.image_ocr_min_confidence)
            max_lines = max(3, int(self._settings.image_analysis_max_lines))
            target_high_conf_lines = max(2, min(4, max_lines))

            for image_array in variants:
                if time.perf_counter() >= deadline:
                    logger.info("rapidocr_timeout_budget_reached")
                    break

                try:
                    result, _ = self._rapid_ocr_engine(image_array)
                except Exception:
                    logger.exception("rapidocr_variant_analysis_failed")
                    continue

                for text, score in self._extract_ocr_lines(result):
                    if not text:
                        continue
                    normalized_text = " ".join(text.split())
                    previous_score = line_scores.get(normalized_text)
                    if previous_score is None:
                        line_scores[normalized_text] = score
                        ordered_lines.append(normalized_text)
                        continue

                    if score > previous_score:
                        line_scores[normalized_text] = score

                high_conf_lines = sum(
                    1
                    for line in ordered_lines
                    if line_scores.get(line, 0.0) >= min_confidence
                )
                if high_conf_lines >= target_high_conf_lines:
                    break

            if not ordered_lines:
                return ""

            primary_lines = [
                line for line in ordered_lines
                if line_scores.get(line, 0.0) >= min_confidence
            ][:max_lines]
            if len(primary_lines) >= 2:
                return self._normalize_extracted_text("\n".join(primary_lines))

            # Keep recall high for document OCR: if strict filtering keeps too little text,
            # relax threshold slightly and keep useful low-confidence lines.
            relaxed_confidence = max(0.2, min_confidence - 0.15)
            relaxed_lines = [
                line for line in ordered_lines
                if line_scores.get(line, 0.0) >= relaxed_confidence
            ][:max_lines]

            return self._normalize_extracted_text("\n".join(relaxed_lines))
        finally:
            self._local_ocr_semaphore.release()

    @staticmethod
    def _extract_ocr_lines(result: list | tuple | None) -> list[tuple[str, float]]:
        lines: list[tuple[str, float]] = []
        for item in result or []:
            if len(item) < 3:
                continue

            text = str(item[1] or "").strip()
            try:
                score = float(item[2])
            except (TypeError, ValueError):
                score = 0.0

            if text:
                lines.append((text, score))

        return lines

    @staticmethod
    def _build_ocr_image_variants(image: Image.Image, np) -> list:
        rgb = image.convert("RGB")
        width, height = rgb.size
        max_edge = max(width, height)

        if max_edge < 1024:
            scale = 1024 / max_edge
            new_size = (
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
            )
            rgb = rgb.resize(new_size, Image.Resampling.LANCZOS)

        sharpened = rgb.filter(ImageFilter.UnsharpMask(radius=1.2, percent=135, threshold=3))
        grayscale = ImageOps.grayscale(sharpened)
        contrasted = ImageOps.autocontrast(grayscale, cutoff=2)

        grayscale_array = np.asarray(contrasted, dtype=np.uint8)
        threshold = int(grayscale_array.mean())
        threshold = min(196, max(72, threshold))
        binary = np.where(grayscale_array >= threshold, 255, 0).astype(np.uint8)
        binary_rgb = np.stack((binary, binary, binary), axis=-1)

        return [
            np.asarray(sharpened),
            np.asarray(contrasted.convert("RGB")),
            binary_rgb,
        ]

    def _build_prompt(self, *, source: str, hint: str) -> str:
        context_line = f"Source: {source}" if source else ""
        hint_line = f"Hint: {hint}" if hint else ""
        prompt_parts = [_DEFAULT_IMAGE_ANALYSIS_PROMPT]
        if context_line:
            prompt_parts.append(context_line)
        if hint_line:
            prompt_parts.append(hint_line)
        return "\n".join(prompt_parts)

    @staticmethod
    def _extract_text_from_gemini_response(payload: dict) -> str:
        candidates = payload.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            texts = [str(part.get("text", "")).strip() for part in parts if part.get("text")]
            merged = "\n".join(texts).strip()
            if merged:
                return ImageUnderstandingService._normalize_extracted_text(merged)
        return ""

    def _clean_analysis_text(self, text: str) -> str:
        normalized = self._normalize_extracted_text(text)
        if not normalized:
            return ""

        max_lines = max(3, int(self._settings.image_analysis_max_lines))
        min_chars = max(4, int(self._settings.image_analysis_min_meaningful_chars))

        cleaned_lines: list[str] = []
        seen: set[str] = set()
        for raw_line in normalized.splitlines():
            line = " ".join(raw_line.split()).strip("-•\t ")
            if not line:
                continue

            normalized_key = line.casefold()
            if normalized_key in seen:
                continue

            if _ANALYSIS_NOISE_RE.search(line):
                continue

            if self._is_garbled_line(line):
                continue

            seen.add(normalized_key)
            cleaned_lines.append(line)
            if len(cleaned_lines) >= max_lines:
                break

        if not cleaned_lines:
            return ""

        merged = "\n".join(cleaned_lines).strip()
        if len("".join(merged.split())) < min_chars:
            return ""

        if not any(_MEANINGFUL_CHAR_RE.search(line) for line in cleaned_lines):
            return ""

        return merged

    @staticmethod
    def _is_garbled_line(line: str) -> bool:
        stripped = line.strip()
        if len(stripped) < 3:
            return True

        if _SYMBOL_ONLY_RE.fullmatch(stripped):
            return True

        alpha_num_chars = sum(ch.isalnum() for ch in stripped)
        symbol_chars = len(stripped) - alpha_num_chars
        if symbol_chars / max(1, len(stripped)) > 0.55:
            return True

        for token in stripped.split():
            if len(token) < 20:
                continue
            if _MEANINGFUL_CHAR_RE.search(token):
                continue
            return True

        return False

    @staticmethod
    def _normalize_extracted_text(text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
        while "\n\n\n" in normalized:
            normalized = normalized.replace("\n\n\n", "\n\n")
        return normalized.strip()
