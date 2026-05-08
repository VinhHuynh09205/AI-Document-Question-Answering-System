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
        self._pipeline_timing_totals_ms: dict[str, float] = defaultdict(float)
        self._pipeline_timing_max_ms: dict[str, float] = defaultdict(float)
        self._pipeline_timing_counts: dict[str, int] = defaultdict(int)
        self._pipeline_timing_last_ms: dict[str, float] = defaultdict(float)
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = defaultdict(float)
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

    def record_pipeline_timing(self, metric_name: str, duration_ms: float) -> None:
        clean_name = str(metric_name or "").strip()
        if not clean_name:
            return

        safe_value = max(0.0, float(duration_ms))
        with self._lock:
            self._pipeline_timing_totals_ms[clean_name] += safe_value
            self._pipeline_timing_counts[clean_name] += 1
            self._pipeline_timing_last_ms[clean_name] = safe_value
            self._pipeline_timing_max_ms[clean_name] = max(
                self._pipeline_timing_max_ms[clean_name],
                safe_value,
            )

    def increment_counter(self, counter_name: str, amount: int = 1) -> None:
        clean_name = str(counter_name or "").strip()
        if not clean_name:
            return
        with self._lock:
            self._counters[clean_name] += int(amount)

    def record_gauge(self, gauge_name: str, value: float) -> None:
        clean_name = str(gauge_name or "").strip()
        if not clean_name:
            return
        with self._lock:
            self._gauges[clean_name] = float(value)

    def snapshot(self) -> dict:
        with self._lock:
            pipeline_timing = {}
            for name, total_value in self._pipeline_timing_totals_ms.items():
                count = max(1, self._pipeline_timing_counts.get(name, 0))
                pipeline_timing[name] = {
                    "count": self._pipeline_timing_counts.get(name, 0),
                    "total_ms": round(total_value, 3),
                    "avg_ms": round(total_value / count, 3),
                    "max_ms": round(self._pipeline_timing_max_ms.get(name, 0.0), 3),
                    "last_ms": round(self._pipeline_timing_last_ms.get(name, 0.0), 3),
                }

            return {
                "uptime_seconds": int(time.time() - self._started_at),
                "total_requests": self._total_requests,
                "status_counts": dict(self._status_counts),
                "endpoint_counts": dict(self._endpoint_counts),
                "fallback_answers": self._fallback_answers,
                "rate_limited_requests": self._rate_limited_requests,
                "pipeline_timing": pipeline_timing,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }
