import base64
import logging
import re
import time
from io import BytesIO
from pathlib import Path

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


class ImageUnderstandingService(IImageUnderstandingService):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rapid_ocr_engine = None
        self._gemini_backoff_until = 0.0
        self._local_vision_backoff_until = 0.0

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

        if not self._looks_like_informative_image(normalized_bytes):
            return ImageAnalysisResult(text="", provider="image_low_signal")

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

        return ImageAnalysisResult(text="", provider="no_result")

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

                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                    buffer = BytesIO()
                    image.save(buffer, format="PNG")
                    return buffer.getvalue(), "image/png"

                return image_bytes, mime_type
        except (UnidentifiedImageError, OSError):
            return b"", ""

    def _looks_like_informative_image(self, image_bytes: bytes) -> bool:
        min_edge_mean = float(self._settings.image_analysis_min_edge_mean)
        min_grayscale_std = float(self._settings.image_analysis_min_grayscale_stddev)

        if min_edge_mean <= 0 and min_grayscale_std <= 0:
            return True

        try:
            with Image.open(BytesIO(image_bytes)) as image:
                grayscale = ImageOps.grayscale(image)
                edges = grayscale.filter(ImageFilter.FIND_EDGES)
                edge_mean = float(ImageStat.Stat(edges).mean[0])
                grayscale_stddev = float(ImageStat.Stat(grayscale).stddev[0])

            if min_edge_mean > 0 and edge_mean < min_edge_mean:
                return False
            if min_grayscale_std > 0 and grayscale_stddev < min_grayscale_std:
                return False
            return True
        except Exception:
            # If preflight quality checks fail unexpectedly, keep the pipeline permissive.
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
        model = self._settings.local_vision_model.strip()
        if not model:
            return ""

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

        for endpoint in self._build_local_vision_endpoints():
            try:
                with httpx.Client(timeout=self._settings.image_analysis_timeout_seconds) as client:
                    response = client.post(endpoint, json=payload)
            except Exception as exc:
                logger.warning(
                    "local_vision_understanding_request_failed source=%s endpoint=%s error_type=%s",
                    source,
                    endpoint,
                    type(exc).__name__,
                )
                self._enter_provider_backoff(
                    "local_vision",
                    f"request_error:{type(exc).__name__}",
                )
                continue

            if response.status_code >= 400:
                logger.warning(
                    "local_vision_understanding_http_error source=%s endpoint=%s status=%s",
                    source,
                    endpoint,
                    response.status_code,
                )
                self._enter_provider_backoff(
                    "local_vision",
                    f"http_{response.status_code}",
                )
                continue

            try:
                data = response.json()
            except ValueError:
                logger.warning(
                    "local_vision_understanding_invalid_json source=%s endpoint=%s",
                    source,
                    endpoint,
                )
                continue

            text = str(data.get("response", "")).strip()
            normalized = self._normalize_extracted_text(text)
            if normalized:
                return normalized

        return ""

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
            resolved.append(endpoint + "/api/generate")

        return resolved

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

        line_scores: dict[str, float] = {}
        ordered_lines: list[str] = []

        for image_array in variants:
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

        if not ordered_lines:
            return ""

        min_confidence = self._settings.image_ocr_min_confidence
        max_lines = max(3, int(self._settings.image_analysis_max_lines))
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

        if max_edge < 1200:
            scale = 1200 / max_edge
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
