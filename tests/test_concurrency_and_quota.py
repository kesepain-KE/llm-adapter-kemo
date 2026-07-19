"""Concurrency admission, quota transactions, and diagnostic log tests."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.call_log import CallLogger
from core.auth import AuthManager
from core.concurrency import (
    ConcurrencyLimitError,
    ConcurrencyManager,
    ConcurrencySettings,
)
from core.quota_store import QuotaStore
from core.usage import QuotaExceededError
from api.services.chat_service import handle_chat


class _RecordingCallLog:
    def __init__(self):
        self.entries = []

    def log(self, **entry):
        self.entries.append(entry)


class ConcurrencyManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_timeout_returns_limit_error(self):
        manager = ConcurrencyManager(ConcurrencySettings(1, 1, 0.02))
        first = await manager.acquire("deepseek")
        with self.assertRaises(ConcurrencyLimitError):
            await manager.acquire("deepseek")
        await first.release()

    async def test_stress_never_exceeds_global_or_provider_limits(self):
        manager = ConcurrencyManager(ConcurrencySettings(8, 3, 2.0))
        peak_global = 0
        peak_by_provider = {"a": 0, "b": 0}

        async def worker(provider: str):
            nonlocal peak_global
            lease = await manager.acquire(provider)
            try:
                snapshot = manager.snapshot()
                peak_global = max(peak_global, snapshot["active"])
                peak_by_provider[provider] = max(
                    peak_by_provider[provider],
                    snapshot["active_by_provider"].get(provider, 0),
                )
                await asyncio.sleep(0.003)
            finally:
                await lease.release()

        await asyncio.gather(*(worker("a" if i % 2 else "b") for i in range(80)))

        self.assertLessEqual(peak_global, 8)
        self.assertLessEqual(peak_by_provider["a"], 3)
        self.assertLessEqual(peak_by_provider["b"], 3)
        self.assertEqual(manager.snapshot()["active"], 0)

    async def test_handle_chat_queue_timeout_returns_429_and_logs_phase(self):
        manager = ConcurrencyManager(ConcurrencySettings(1, 1, 0.02))
        blocker = await manager.acquire("deepseek")
        call_log = _RecordingCallLog()
        ctx = SimpleNamespace(
            auth=SimpleNamespace(
                authenticate=lambda token, model: {"name": "test-key"}
            ),
            router=SimpleNamespace(
                resolve=lambda model: {
                    "provider": "deepseek",
                    "model": "vendor-model",
                    "capability": "chat",
                    "capabilities": ["chat"],
                }
            ),
            usage=SimpleNamespace(check_quota=lambda token: None),
            registry=SimpleNamespace(get_chat=lambda provider: object()),
            concurrency=manager,
            call_log=call_log,
        )

        try:
            with self.assertRaises(HTTPException) as raised:
                await handle_chat(
                    ctx,
                    "test-key",
                    {"model": "public-model", "messages": []},
                    stream=False,
                )
        finally:
            await blocker.release()

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.detail["error"]["code"], "gateway_busy")
        self.assertEqual(raised.exception.headers["Retry-After"], "1")
        self.assertEqual(len(call_log.entries), 1)
        self.assertEqual(call_log.entries[0]["error_phase"], "gateway_queue")
        self.assertTrue(call_log.entries[0]["request_id"].startswith("votx-"))
        self.assertEqual(manager.snapshot()["active"], 0)


class QuotaStoreTests(unittest.TestCase):
    def _root(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "config").mkdir(parents=True)
        (root / "config" / "api_keys.json").write_text(
            json.dumps({
                "keys": {
                    "test-key": {
                        "quota": {"total_tokens": 100000, "used_tokens": 10}
                    }
                }
            }),
            encoding="utf-8",
        )
        return temp, root

    def test_imports_existing_json_counter_once(self):
        temp, root = self._root()
        self.addCleanup(temp.cleanup)
        store = QuotaStore(root)
        self.assertEqual(store.get_used("test-key"), 10)

        data = json.loads((root / "config" / "api_keys.json").read_text("utf-8"))
        data["keys"]["test-key"]["quota"]["used_tokens"] = 999
        (root / "config" / "api_keys.json").write_text(json.dumps(data), "utf-8")
        store.sync_from_config(overwrite=False)
        self.assertEqual(store.get_used("test-key"), 10)

    def test_concurrent_deductions_are_atomic(self):
        temp, root = self._root()
        self.addCleanup(temp.cleanup)
        store = QuotaStore(root)

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: store.deduct("test-key", 1), range(100)))

        self.assertEqual(max(results), 110)
        self.assertEqual(store.get_used("test-key"), 110)
        configured = json.loads(
            (root / "config" / "api_keys.json").read_text("utf-8")
        )
        self.assertEqual(
            configured["keys"]["test-key"]["quota"]["used_tokens"], 10
        )

    def test_authentication_reads_authoritative_sqlite_counter(self):
        temp, root = self._root()
        self.addCleanup(temp.cleanup)
        data = json.loads((root / "config" / "api_keys.json").read_text("utf-8"))
        data["keys"]["test-key"]["models"] = ["test-model"]
        data["keys"]["test-key"]["quota"]["total_tokens"] = 15
        (root / "config" / "api_keys.json").write_text(json.dumps(data), "utf-8")

        store = QuotaStore(root)
        store.deduct("test-key", 6)
        auth = AuthManager(root)
        auth.bind_quota_reader(store.get_used)

        with self.assertRaises(QuotaExceededError):
            auth.authenticate("test-key", "test-model")


class DiagnosticLogTests(unittest.TestCase):
    def test_empty_connect_error_records_cause_and_non_empty_message(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        logger = CallLogger(temp.name)
        exc = httpx.ConnectError("")
        exc.__cause__ = OSError("DNS lookup failed")

        entry = logger.log(
            key_id="test-key",
            key_name="test",
            provider="test-provider",
            model="test-model",
            request={"stream": True, "messages": []},
            response={},
            exception=exc,
            error_phase="upstream_connect",
            attempt_count=3,
        )

        self.assertEqual(entry["error_type"], "ConnectError")
        self.assertIn("DNS lookup failed", entry["error"])
        self.assertEqual(entry["error_phase"], "upstream_connect")
        self.assertEqual(entry["attempt_count"], 3)
        self.assertEqual(entry["error_causes"][0]["type"], "OSError")


if __name__ == "__main__":
    unittest.main()
