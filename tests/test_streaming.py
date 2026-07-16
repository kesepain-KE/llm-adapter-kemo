"""Streaming regression tests for the gateway SSE contract."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.routes.v1 import chat_completions
from api.services.chat_service import _stream_generator
from core.concurrency import ConcurrencyManager, ConcurrencySettings
from provider.deepseek.chat import DeepSeekChat


class _CallLog:
    def __init__(self):
        self.entries = []

    def log(self, **entry):
        self.entries.append(entry)


class _Usage:
    def count(self, provider, response, request=None):
        return response.get("usage") or {}


class _Ctx:
    def __init__(self):
        self.call_log = _CallLog()
        self.usage = _Usage()


class _FakeChat:
    def __init__(self, chunks=(), error: Exception | None = None):
        self.chunks = list(chunks)
        self.error = error

    async def invoke_stream(self, body):
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error


class _DelayedChat:
    async def invoke_stream(self, body):
        await asyncio.sleep(0.04)
        yield {"id": "x", "choices": [{"delta": {"content": "ready"}}]}


class _NeverChat:
    async def invoke_stream(self, body):
        await asyncio.Event().wait()
        if False:  # pragma: no cover - makes this an async generator
            yield {}


class _ConnectFlakyChat:
    def __init__(self, fail_after_chunk: bool = False):
        self.attempts = 0
        self.fail_after_chunk = fail_after_chunk

    async def invoke_stream(self, body):
        self.attempts += 1
        if self.fail_after_chunk:
            yield {"id": "x", "choices": [{"delta": {"content": "partial"}}]}
            raise httpx.ConnectError("connect reset after output")
        if self.attempts == 1:
            raise httpx.ConnectError("temporary connect failure")
        yield {"id": "x", "choices": [{"delta": {"content": "recovered"}}]}


class _FakeResponse:
    def __init__(self, parts):
        self.parts = parts

    async def aiter_lines(self):
        buffer = ""
        for part in self.parts:
            buffer += part.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                yield line
        if buffer:
            yield buffer


class _FakeRequest:
    headers = {"Authorization": "Bearer test-token"}

    async def json(self):
        return {"model": "test", "messages": [], "stream": True}


def _decode_sse(items: list[str]):
    events = []
    for item in items:
        assert item.startswith("data: ")
        payload = item[6:].strip()
        events.append(payload if payload == "[DONE]" else json.loads(payload))
    return events


class StreamResponseHeaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_response_disables_proxy_buffering(self):
        async def result_stream():
            yield "data: [DONE]\n\n"

        with patch("api.routes.v1.get_ctx", return_value=object()), patch(
            "api.routes.v1.handle_chat", new=AsyncMock(return_value=result_stream())
        ):
            response = await chat_completions(_FakeRequest())

        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        self.assertIn("no-transform", response.headers["cache-control"])


class GatewayStreamContractTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, chat, lease=None):
        ctx = _Ctx()
        result = []
        async for item in _stream_generator(
            chat,
            {"model": "vendor-model", "messages": []},
            ctx,
            "test-token",
            {"name": "test"},
            "deepseek",
            "vendor-model",
            "chat",
            0.0,
            lease=lease,
        ):
            result.append(item)
        return _decode_sse(result), ctx

    async def test_normal_chunks_end_with_exactly_one_done(self):
        manager = ConcurrencyManager(ConcurrencySettings(1, 1, 1.0))
        lease = await manager.acquire("deepseek")
        chunks = [
            {"id": "x", "choices": [{"delta": {"content": "a"}}]},
            {"id": "x", "choices": [{"delta": {"content": "b"}}]},
            {"id": "x", "choices": [], "usage": {"completion_tokens": 2}},
        ]
        events, ctx = await self._run(_FakeChat(chunks), lease=lease)
        self.assertEqual(events[:-1], chunks)
        self.assertEqual(events.count("[DONE]"), 1)
        self.assertNotIn("error", ctx.call_log.entries[-1])
        self.assertEqual(manager.snapshot()["active"], 0)

    async def test_disconnect_before_first_event_is_error_without_done(self):
        manager = ConcurrencyManager(ConcurrencySettings(1, 1, 1.0))
        lease = await manager.acquire("deepseek")
        events, ctx = await self._run(
            _FakeChat(error=ConnectionError("before first event")), lease=lease
        )
        self.assertEqual(len(events), 1)
        self.assertIn("error", events[0])
        self.assertNotIn("[DONE]", events)
        self.assertIn("error", ctx.call_log.entries[-1])
        self.assertEqual(manager.snapshot()["active"], 0)

    async def test_disconnect_after_text_is_error_without_done(self):
        first = {"id": "x", "choices": [{"delta": {"content": "partial"}}]}
        events, _ = await self._run(_FakeChat([first], ConnectionError("mid-stream")))
        self.assertEqual(events[0], first)
        self.assertIn("error", events[-1])
        self.assertNotIn("[DONE]", events)

    async def test_disconnect_during_tool_arguments_is_error_without_done(self):
        partial_tool = {
            "id": "x",
            "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "run", "arguments": "{\"pa"}}]}}],
        }
        events, _ = await self._run(_FakeChat([partial_tool], ConnectionError("tool truncated")))
        self.assertEqual(events[0], partial_tool)
        self.assertIn("error", events[-1])
        self.assertNotIn("[DONE]", events)

    async def test_explicit_upstream_sse_error_is_structured_without_done(self):
        events, _ = await self._run(_FakeChat(error=RuntimeError("upstream SSE error: overloaded")))
        error = events[0]["error"]
        self.assertIsInstance(error, dict)
        self.assertEqual(error["type"], "upstream_stream_error")
        self.assertIn("overloaded", error["message"])
        self.assertNotIn("[DONE]", events)

    async def test_slow_first_chunk_emits_heartbeat_without_cancelling_upstream(self):
        ctx = _Ctx()
        result = []
        with patch("api.services.chat_service.STREAM_HEARTBEAT_SECONDS", 0.01):
            async for item in _stream_generator(
                _DelayedChat(),
                {"model": "vendor-model", "messages": []},
                ctx,
                "test-token",
                {"name": "test"},
                "deepseek",
                "vendor-model",
                "chat",
                0.0,
            ):
                result.append(item)

        heartbeats = [item for item in result if item.startswith(": keep-alive")]
        data_events = _decode_sse([item for item in result if item.startswith("data: ")])
        self.assertGreaterEqual(len(heartbeats), 1)
        self.assertEqual(data_events[0]["choices"][0]["delta"]["content"], "ready")
        self.assertEqual(data_events[-1], "[DONE]")

    async def test_downstream_cancellation_is_logged_and_propagated(self):
        ctx = _Ctx()
        manager = ConcurrencyManager(ConcurrencySettings(1, 1, 1.0))
        lease = await manager.acquire("deepseek")
        stream = _stream_generator(
            _NeverChat(),
            {"model": "vendor-model", "messages": []},
            ctx,
            "test-token",
            {"name": "test"},
            "deepseek",
            "vendor-model",
            "chat",
            0.0,
            lease=lease,
        )
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        pending.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await pending

        self.assertEqual(len(ctx.call_log.entries), 1)
        self.assertIn("downstream client disconnected", ctx.call_log.entries[0]["error"])
        self.assertEqual(manager.snapshot()["active"], 0)

    async def test_connect_error_before_first_chunk_is_retried(self):
        chat = _ConnectFlakyChat()
        with patch("api.services.chat_service.CONNECT_RETRIES", 2), patch(
            "api.services.chat_service._connect_retry_delay", return_value=0
        ):
            events, ctx = await self._run(chat)

        self.assertEqual(chat.attempts, 2)
        self.assertEqual(events[0]["choices"][0]["delta"]["content"], "recovered")
        self.assertEqual(events[-1], "[DONE]")
        self.assertEqual(ctx.call_log.entries[-1]["attempt_count"], 2)

    async def test_connect_error_after_first_chunk_is_not_retried(self):
        chat = _ConnectFlakyChat(fail_after_chunk=True)
        with patch("api.services.chat_service.CONNECT_RETRIES", 2), patch(
            "api.services.chat_service._connect_retry_delay", return_value=0
        ):
            events, ctx = await self._run(chat)

        self.assertEqual(chat.attempts, 1)
        self.assertEqual(events[0]["choices"][0]["delta"]["content"], "partial")
        self.assertIn("error", events[-1])
        self.assertNotIn("[DONE]", events)
        self.assertEqual(ctx.call_log.entries[-1]["attempt_count"], 1)


class DeepSeekSSEParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_fragmented_sse_requires_and_accepts_done(self):
        response = _FakeResponse([
            b'data: {"choices":[{"delta":{"content":"a"}}]}\n',
            b'\ndata: [DO',
            b'NE]\n\n',
        ])
        parser = DeepSeekChat.__new__(DeepSeekChat)
        chunks = [chunk async for chunk in parser._parse_sse(response)]
        self.assertEqual(chunks[0]["choices"][0]["delta"]["content"], "a")

    async def test_eof_before_done_is_failure(self):
        response = _FakeResponse([b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'])
        parser = DeepSeekChat.__new__(DeepSeekChat)
        with self.assertRaisesRegex(Exception, "DONE"):
            _ = [chunk async for chunk in parser._parse_sse(response)]

    async def test_explicit_error_event_is_failure(self):
        response = _FakeResponse([b'data: {"error":{"message":"overloaded"}}\n\n'])
        parser = DeepSeekChat.__new__(DeepSeekChat)
        with self.assertRaisesRegex(Exception, "overloaded"):
            _ = [chunk async for chunk in parser._parse_sse(response)]


if __name__ == "__main__":
    unittest.main()
