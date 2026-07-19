"""In-process concurrency admission control for upstream chat calls."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from dataclasses import dataclass


logger = logging.getLogger(__name__)


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("invalid %s=%r; using %d", name, raw, default)
        return default
    if value < 1:
        logger.warning("%s must be positive; using %d", name, default)
        return default
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("invalid %s=%r; using %.1f", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s must be positive; using %.1f", name, default)
        return default
    return value


@dataclass(frozen=True)
class ConcurrencySettings:
    global_limit: int
    provider_limit: int
    queue_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "ConcurrencySettings":
        return cls(
            global_limit=_positive_int("VOTX_CHAT_GLOBAL_CONCURRENCY", 32),
            provider_limit=_positive_int("VOTX_CHAT_PROVIDER_CONCURRENCY", 16),
            queue_timeout_seconds=_positive_float("VOTX_CHAT_QUEUE_TIMEOUT", 10.0),
        )


class ConcurrencyLimitError(Exception):
    """Raised when a request cannot enter the upstream concurrency window."""

    def __init__(self, provider: str, settings: ConcurrencySettings):
        super().__init__(
            f"chat concurrency queue timed out for provider '{provider}' "
            f"after {settings.queue_timeout_seconds:g}s"
        )
        self.provider = provider
        self.retry_after = max(1, int(settings.queue_timeout_seconds))


class ConcurrencyLease:
    """Idempotent lease returned by :class:`ConcurrencyManager`."""

    def __init__(self, manager: "ConcurrencyManager", provider: str):
        self._manager = manager
        self.provider = provider
        self._released = False

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._manager._release(self.provider)


class ConcurrencyManager:
    """Global and per-provider concurrency gate for one server process."""

    def __init__(self, settings: ConcurrencySettings | None = None):
        self.settings = settings or ConcurrencySettings.from_env()
        self._condition = asyncio.Condition()
        self._active_global = 0
        self._active_by_provider: dict[str, int] = defaultdict(int)
        self._waiting_global = 0
        self._waiting_by_provider: dict[str, int] = defaultdict(int)

    def _has_capacity(self, provider: str) -> bool:
        return (
            self._active_global < self.settings.global_limit
            and self._active_by_provider[provider] < self.settings.provider_limit
        )

    async def acquire(self, provider: str) -> ConcurrencyLease:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.queue_timeout_seconds
        async with self._condition:
            self._waiting_global += 1
            self._waiting_by_provider[provider] += 1
            try:
                while not self._has_capacity(provider):
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise ConcurrencyLimitError(provider, self.settings)
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                    except asyncio.TimeoutError as exc:
                        raise ConcurrencyLimitError(provider, self.settings) from exc

                self._active_global += 1
                self._active_by_provider[provider] += 1
                return ConcurrencyLease(self, provider)
            finally:
                self._waiting_global -= 1
                self._waiting_by_provider[provider] -= 1
                if self._waiting_by_provider[provider] <= 0:
                    self._waiting_by_provider.pop(provider, None)

    async def _release(self, provider: str) -> None:
        async with self._condition:
            self._active_global = max(0, self._active_global - 1)
            self._active_by_provider[provider] = max(
                0, self._active_by_provider[provider] - 1
            )
            if self._active_by_provider[provider] <= 0:
                self._active_by_provider.pop(provider, None)
            self._condition.notify_all()

    def snapshot(self) -> dict:
        return {
            "global_limit": self.settings.global_limit,
            "provider_limit": self.settings.provider_limit,
            "queue_timeout_seconds": self.settings.queue_timeout_seconds,
            "active": self._active_global,
            "waiting": self._waiting_global,
            "active_by_provider": dict(self._active_by_provider),
            "waiting_by_provider": dict(self._waiting_by_provider),
        }
