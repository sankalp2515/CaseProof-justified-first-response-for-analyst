"""Measure practice-session bootstrap latency (B11) against a running local stack.

Usage: python -m eval.practice_bootstrap [base_url] [label]
Creates isolated synthetic practice sessions only; never creates a complaint.
"""

import concurrent.futures
import json
import statistics
import sys
import time
import urllib.request


def create(base):
    started = time.perf_counter()
    request = urllib.request.Request(base + "/v1/victim/demo-session", method="POST", data=b"")
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.load(response)
    assert body["complaints_created"] == 0 and body["synthetic"] is True
    return time.perf_counter() - started


def summarise(samples):
    ordered = sorted(samples)
    return {
        "n": len(ordered),
        "median_s": round(statistics.median(ordered), 3),
        "p95_s": round(ordered[max(0, round(0.95 * len(ordered)) - 1)], 3),
        "max_s": round(ordered[-1], 3),
    }


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
    label = sys.argv[2] if len(sys.argv) > 2 else "idle"
    sequential = [create(base) for _ in range(10)]
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        concurrent_samples = list(pool.map(lambda _: create(base), range(10)))
    print(
        json.dumps(
            {
                "label": label,
                "sequential": summarise(sequential),
                "concurrent_5": summarise(concurrent_samples),
            }
        )
    )


if __name__ == "__main__":
    main()
