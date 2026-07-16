"""Core-owned lifecycle tests for external Provider modules."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.registry import Registry
from api.app import lifespan


class _AsyncClose:
    def __init__(self):
        self.calls = 0

    async def close(self):
        self.calls += 1


class _AsyncAclose:
    def __init__(self):
        self.calls = 0

    async def aclose(self):
        self.calls += 1


class _SyncClose:
    def __init__(self):
        self.calls = 0

    def close(self):
        self.calls += 1


class _BrokenClose:
    def __init__(self):
        self.calls = 0

    def close(self):
        self.calls += 1
        raise RuntimeError("cleanup failed")


class RegistryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def _registry_root(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "provider" / "external").mkdir(parents=True)
        (root / "config").mkdir()
        (root / "provider" / "external" / "model.json").write_text(
            json.dumps({
                "provider": "external",
                "enabled": True,
                "modules": {"chat": "chat"},
                "models": {},
            }),
            encoding="utf-8",
        )
        return temp, root

    @staticmethod
    def _write_enabled(root: Path, enabled: bool) -> None:
        (root / "config" / "config.json").write_text(
            json.dumps({"providers": {"external": {"enabled": enabled}}}),
            encoding="utf-8",
        )

    async def test_load_all_reuses_instance_and_honors_disabled_state(self):
        temp, root = self._registry_root()
        self.addCleanup(temp.cleanup)
        self._write_enabled(root, True)
        registry = Registry(root)
        external = object()
        registry._modules[("external", "chat")] = external

        registry.load_all()
        self.assertIs(registry.get_chat("external"), external)
        registry.load_all()
        self.assertIs(registry.get_chat("external"), external)

        self._write_enabled(root, False)
        registry.load_all()
        with self.assertRaises(ModuleNotFoundError):
            registry.get_chat("external")

        self._write_enabled(root, True)
        registry.load_all()
        self.assertIs(registry.get_chat("external"), external)

    async def test_aclose_supports_optional_cleanup_and_deduplicates(self):
        registry = Registry()
        async_close = _AsyncClose()
        async_aclose = _AsyncAclose()
        sync_close = _SyncClose()
        broken_close = _BrokenClose()
        registry._modules = {
            ("a", "chat"): async_close,
            ("a", "vision"): async_close,
            ("b", "chat"): async_aclose,
            ("c", "chat"): sync_close,
            ("d", "chat"): broken_close,
            ("e", "chat"): object(),
        }

        with self.assertLogs("core.registry", level="WARNING"):
            await registry.aclose()

        self.assertEqual(async_close.calls, 1)
        self.assertEqual(async_aclose.calls, 1)
        self.assertEqual(sync_close.calls, 1)
        self.assertEqual(broken_close.calls, 1)
        self.assertEqual(registry._modules, {})

    async def test_app_lifespan_closes_lazy_context(self):
        with patch("api.app.close_ctx", new_callable=AsyncMock) as close_ctx:
            async with lifespan(None):
                close_ctx.assert_not_awaited()
        close_ctx.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
