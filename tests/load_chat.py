"""Opt-in streaming load test for a running VOTX Gateway.

The API key is read only from ``VOTX_LOAD_TEST_API_KEY`` so it does not appear
in the process command line. This file is intentionally excluded from unittest
discovery; run it explicitly against an approved target.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import Counter
from dataclasses import dataclass

import httpx


@dataclass
class Result:
    ok: bool
    status: int
    elapsed_ms: float
    first_event_ms: float | None
    error: str = ""


def percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * pct / 100)
    return round(ordered[index], 2)


async def run_one(client: httpx.AsyncClient, url: str, model: str) -> Result:
    started = time.perf_counter()
    first_event_ms = None
    try:
        async with client.stream(
            "POST",
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "stream": True,
                "max_tokens": 8,
            },
        ) as response:
            if response.status_code != 200:
                body = (await response.aread()).decode("utf-8", errors="replace")
                return Result(
                    False,
                    response.status_code,
                    (time.perf_counter() - started) * 1000,
                    None,
                    body[:240],
                )

            done = False
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if first_event_ms is None:
                    first_event_ms = (time.perf_counter() - started) * 1000
                if payload == "[DONE]":
                    done = True
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if event.get("error"):
                    return Result(
                        False,
                        response.status_code,
                        (time.perf_counter() - started) * 1000,
                        first_event_ms,
                        json.dumps(event["error"], ensure_ascii=False)[:240],
                    )

            return Result(
                done,
                response.status_code,
                (time.perf_counter() - started) * 1000,
                first_event_ms,
                "" if done else "stream closed before [DONE]",
            )
    except Exception as exc:
        return Result(
            False,
            0,
            (time.perf_counter() - started) * 1000,
            first_event_ms,
            f"{type(exc).__name__}: {exc}",
        )


async def main(args) -> int:
    api_key = os.environ.get("VOTX_LOAD_TEST_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("VOTX_LOAD_TEST_API_KEY is required")

    queue: asyncio.Queue[int] = asyncio.Queue()
    for index in range(args.requests):
        queue.put_nowait(index)

    results: list[Result] = []
    limits = httpx.Limits(
        max_connections=args.concurrency,
        max_keepalive_connections=args.concurrency,
        keepalive_expiry=30.0,
    )
    timeout = httpx.Timeout(args.timeout, connect=10.0, pool=10.0)
    headers = {"Authorization": f"Bearer {api_key}"}
    url = args.base_url.rstrip("/") + "/v1/chat/completions"

    async with httpx.AsyncClient(headers=headers, limits=limits, timeout=timeout) as client:
        async def worker():
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    results.append(await run_one(client, url, args.model))
                finally:
                    queue.task_done()

        started = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(args.concurrency)))
        wall_ms = (time.perf_counter() - started) * 1000

    elapsed = [result.elapsed_ms for result in results]
    first = [result.first_event_ms for result in results if result.first_event_ms is not None]
    errors = Counter(result.error for result in results if not result.ok)
    summary = {
        "requests": len(results),
        "concurrency": args.concurrency,
        "success": sum(1 for result in results if result.ok),
        "failed": sum(1 for result in results if not result.ok),
        "wall_ms": round(wall_ms, 2),
        "throughput_rps": round(len(results) / max(wall_ms / 1000, 0.001), 2),
        "latency_ms": {
            "p50": percentile(elapsed, 50),
            "p95": percentile(elapsed, 95),
            "p99": percentile(elapsed, 99),
        },
        "first_event_ms": {
            "p50": percentile(first, 50),
            "p95": percentile(first, 95),
            "p99": percentile(first, 99),
        },
        "status_counts": dict(Counter(result.status for result in results)),
        "errors": dict(errors.most_common(10)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def parse_args():
    parser = argparse.ArgumentParser(description="Load test a VOTX streaming chat endpoint")
    parser.add_argument("--base-url", default="http://127.0.0.1:8741")
    parser.add_argument("--model", required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    if args.concurrency < 1 or args.requests < 1:
        parser.error("concurrency and requests must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parse_args())))
