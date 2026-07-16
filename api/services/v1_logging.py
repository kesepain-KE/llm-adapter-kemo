"""Shared logging helpers for OpenAI-compatible /v1 routes."""

from __future__ import annotations

import time
from typing import Any

from core.call_log import exception_message


def log_v1_success(
    ctx,
    *,
    token: str,
    key_info: dict[str, Any],
    provider: str,
    model: str,
    capability: str,
    request: dict[str, Any],
    response: dict[str, Any] | None,
    started_at: float,
) -> None:
    """Write a successful /v1 call log entry and deduct quota when usage exists."""
    latency_ms = (time.perf_counter() - started_at) * 1000
    usage: dict[str, Any] = {}
    if isinstance(response, dict) and response.get("usage"):
        usage = ctx.usage.count(provider, response, request=request)

    ctx.call_log.log(
        key_id=token,
        key_name=key_info.get("name", token[:12]),
        provider=provider,
        model=model,
        capability=capability,
        request=request,
        response=response if isinstance(response, dict) else {},
        usage=usage,
        latency_ms=latency_ms,
        completion_latency_ms=latency_ms,
    )


def log_v1_error(
    ctx,
    *,
    token: str,
    key_info: dict[str, Any],
    provider: str,
    model: str,
    capability: str,
    request: dict[str, Any],
    started_at: float,
    error: Exception,
) -> None:
    """Write a failed /v1 call log entry."""
    latency_ms = (time.perf_counter() - started_at) * 1000
    ctx.call_log.log(
        key_id=token,
        key_name=key_info.get("name", token[:12]),
        provider=provider,
        model=model,
        capability=capability,
        request=request,
        response={},
        error=f"{type(error).__name__}: {exception_message(error)}",
        exception=error,
        error_phase="upstream_request",
        latency_ms=latency_ms,
        completion_latency_ms=latency_ms,
    )
