import argparse
import sys
from tempfile import NamedTemporaryFile

import httpx


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_smoke(base_url: str, timeout: float) -> None:
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        health = client.get("/api/v1/health")
        _assert(health.status_code == 200, "health check failed")

        readiness = client.get("/api/v1/health/ready")
        _assert(readiness.status_code == 200, "readiness check failed")

        metrics = client.get("/api/v1/metrics")
        _assert(metrics.status_code == 200, "metrics endpoint failed")

        with NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=True) as handle:
            handle.write("FastAPI la framework Python de xay dung API nhanh.")
            handle.flush()

            with open(handle.name, "rb") as file_handle:
                upload = client.post(
                    "/api/v1/upload",
                    files={"files": ("smoke.md", file_handle, "text/markdown")},
                )
            _assert(upload.status_code == 200, "upload endpoint failed")

        ask = client.post("/api/v1/ask", json={"question": "FastAPI la gi?"})
        _assert(ask.status_code == 200, "ask endpoint failed")

        payload = ask.json()
        _assert(bool(payload.get("answer")), "ask answer is empty")

    print("Smoke test passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for AIChatBox API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    try:
        run_smoke(base_url=args.base_url, timeout=args.timeout)
    except Exception as exc:
        print(f"Smoke test failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
