import time
from collections import defaultdict
from threading import Lock

from app.services.interfaces.runtime_metrics import IRuntimeMetrics


class RuntimeMetrics(IRuntimeMetrics):
    def __init__(self) -> None:
        self._started_at = time.time()
        self._total_requests = 0
        self._status_counts: dict[str, int] = defaultdict(int)
        self._endpoint_counts: dict[str, int] = defaultdict(int)
        self._fallback_answers = 0
        self._rate_limited_requests = 0
        self._lock = Lock()

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        endpoint_key = f"{method.upper()} {path}"
        status_key = str(status_code)

        with self._lock:
            self._total_requests += 1
            self._status_counts[status_key] += 1
            self._endpoint_counts[endpoint_key] += 1

    def increment_fallback_answers(self) -> None:
        with self._lock:
            self._fallback_answers += 1

    def increment_rate_limited_requests(self) -> None:
        with self._lock:
            self._rate_limited_requests += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "uptime_seconds": int(time.time() - self._started_at),
                "total_requests": self._total_requests,
                "status_counts": dict(self._status_counts),
                "endpoint_counts": dict(self._endpoint_counts),
                "fallback_answers": self._fallback_answers,
                "rate_limited_requests": self._rate_limited_requests,
            }
