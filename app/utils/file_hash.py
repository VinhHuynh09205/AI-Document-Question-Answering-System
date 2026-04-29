from __future__ import annotations

import hashlib
from pathlib import Path


def compute_file_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    """Return (sha256_hex, file_size_bytes) for a file path."""
    hasher = hashlib.sha256()
    total_size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            total_size += len(chunk)
    return hasher.hexdigest(), total_size
