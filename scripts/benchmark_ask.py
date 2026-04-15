import argparse
import statistics
import time

import httpx


def run_benchmark(base_url: str, question: str, runs: int, timeout: float) -> None:
    latencies_ms: list[float] = []
    success = 0

    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        for _ in range(runs):
            started = time.perf_counter()
            response = client.post("/api/v1/ask", json={"question": question})
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies_ms.append(elapsed_ms)

            if response.status_code == 200:
                success += 1

    p50 = statistics.median(latencies_ms) if latencies_ms else 0.0
    p95 = _percentile(latencies_ms, 95)

    print(f"Runs: {runs}")
    print(f"Success: {success}/{runs}")
    print(f"Mean latency (ms): {statistics.mean(latencies_ms):.2f}")
    print(f"P50 latency (ms): {p50:.2f}")
    print(f"P95 latency (ms): {p95:.2f}")


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = int((percentile / 100) * (len(ordered) - 1))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark /ask endpoint")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--question", default="Tai lieu noi gi?")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    run_benchmark(
        base_url=args.base_url,
        question=args.question,
        runs=max(1, args.runs),
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
