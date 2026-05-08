from __future__ import annotations

import hashlib
from collections import OrderedDict
from threading import Lock


class InMemoryEmbeddingCache:
    def __init__(self, *, enabled: bool = True, max_entries: int = 50000) -> None:
        self._enabled = bool(enabled)
        self._max_entries = max(100, int(max_entries))
        self._store: OrderedDict[str, list[float]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(str(text or "").encode("utf-8", errors="ignore")).hexdigest()

    def get(self, key: str) -> list[float] | None:
        if not self._enabled:
            return None

        with self._lock:
            value = self._store.get(key)
            if value is None:
                self._misses += 1
                return None

            self._store.move_to_end(key)
            self._hits += 1
            return list(value)

    def set(self, key: str, value: list[float]) -> None:
        if not self._enabled:
            return

        with self._lock:
            self._store[key] = list(value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._store),
            }
