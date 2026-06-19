"""
StepFun 聊天适配器。

将统一格式的聊天请求转换为 StepFun API 调用，
处理 stream / non-stream、tool calls。

StepFun API 为 OpenAI-compatible，端点位于 /v1/chat/completions。

API 文档: https://platform.stepfun.com/docs/overview
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.stepfun.com"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------

class StepFunError(Exception):
    """StepFun API 通用错误。"""


class StepFunAuthError(StepFunError):
    """API Key 缺失或无效。"""


class StepFunAPIError(StepFunError):
    """API 返回错误响应。"""

    def __init__(self, status_code: int, message: str, body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# ---------------------------------------------------------------------------
# 适配器
# ---------------------------------------------------------------------------

class StepFunChat:
    """StepFun 聊天适配器。

    用法::

        chat = StepFunChat(config=model_json)
        response = await chat.invoke(request)
        # 或流式：
        async for chunk in chat.invoke_stream(request):
            ...
    """

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ):
        """初始化适配器。"""
        cfg = config or {}

        self._base_url: str = (
            cfg.get("base_url") or os.environ.get("STEPFUN_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")

        self._api_key: str = (
            os.environ.get(cfg.get("api_key_env", "STEPFUN_API_KEY")) or ""
        )

        self._enabled: bool = cfg.get("enabled", True)

        # 模型配置
        self._models: dict[str, dict[str, Any]] = cfg.get("models", {})

        # HTTP 客户端
        self._client: httpx.AsyncClient = http_client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
        )

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        """非流式聊天补全。"""
        self._check_enabled()
        self._check_auth()

        body = self._build_request_body(request)
        body["stream"] = False

        api_path = request.get("api_path", "/v1/chat/completions")
        url = f"{self._base_url}{api_path}"
        headers = self._build_headers()

        logger.debug("invoke url=%s model=%s", url, body.get("model"))

        response = await self._client.post(url, json=body, headers=headers)

        if response.status_code != 200:
            raise self._make_api_error(response)

        data: dict[str, Any] = response.json()
        return self._normalize_response(data)

    async def invoke_stream(
        self, request: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """流式聊天补全。"""
        self._check_enabled()
        self._check_auth()

        body = self._build_request_body(request)
        body["stream"] = True

        if "stream_options" not in body:
            body["stream_options"] = {"include_usage": True}

        api_path = request.get("api_path", "/v1/chat/completions")
        url = f"{self._base_url}{api_path}"
        headers = self._build_headers()

        logger.debug("invoke_stream url=%s model=%s", url, body.get("model"))

        async with self._client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code != 200:
                raise self._make_api_error(resp)

            async for chunk in self._parse_sse(resp):
                yield self._normalize_stream_chunk(chunk)

    # ------------------------------------------------------------------
    # 内部 — 请求构建
    # ------------------------------------------------------------------

    def _build_request_body(self, request: dict[str, Any]) -> dict[str, Any]:
        """构建 StepFun API 请求体。"""
        body: dict[str, Any] = {
            "model": request.get("model", "step-3.7-flash"),
            "messages": request.get("messages", []),
        }

        # ---- 基础参数 ----
        for param in ("temperature", "top_p", "max_tokens", "stop", "user"):
            if param in request:
                body[param] = request[param]

        # ---- tools / tool_choice ----
        tools = request.get("tools")
        if tools:
            body["tools"] = tools

        tool_choice = request.get("tool_choice")
        if tool_choice is not None:
            body["tool_choice"] = tool_choice

        # ---- response_format (json_object) ----
        response_format = request.get("response_format")
        if response_format is not None:
            body["response_format"] = response_format

        # ---- stream_options ----
        stream_options = request.get("stream_options")
        if stream_options is not None:
            body["stream_options"] = stream_options

        # ---- reasoning_effort (推理强度: low/medium/high) ----
        reasoning_effort = request.get("reasoning_effort")
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort

        # ---- reasoning_format (推理格式: general/deepseek-style) ----
        reasoning_format = request.get("reasoning_format")
        if reasoning_format is not None:
            body["reasoning_format"] = reasoning_format

        # ---- frequency_penalty / presence_penalty ----
        for param in ("frequency_penalty", "presence_penalty"):
            if param in request:
                body[param] = request[param]

        # ---- n (候选数) ----
        if "n" in request:
            body["n"] = request["n"]

        return body

    def _build_headers(self) -> dict[str, str]:
        """构建 HTTP 请求头。"""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # 内部 — 响应归一化
    # ------------------------------------------------------------------

    def _normalize_response(
        self, data: dict[str, Any]
    ) -> dict[str, Any]:
        """将 StepFun API 响应归一化为统一格式 (OpenAI-compatible)。"""
        return {
            "id": data.get("id", ""),
            "object": data.get("object", "chat.completion"),
            "created": data.get("created", int(time.time())),
            "model": data.get("model", "step-3.7-flash"),
            "choices": data.get("choices", []),
            "usage": data.get("usage"),
            "system_fingerprint": data.get("system_fingerprint", ""),
        }

    def _normalize_stream_chunk(
        self, chunk: dict[str, Any]
    ) -> dict[str, Any]:
        """将 SSE chunk 归一化为统一格式。"""
        return {
            "id": chunk.get("id", ""),
            "object": chunk.get("object", "chat.completion.chunk"),
            "created": chunk.get("created", 0),
            "model": chunk.get("model", "step-3.7-flash"),
            "choices": chunk.get("choices", []),
            "usage": chunk.get("usage"),
        }

    # ------------------------------------------------------------------
    # 内部 — SSE 解析
    # ------------------------------------------------------------------

    async def _parse_sse(
        self, response: httpx.Response
    ) -> AsyncIterator[dict[str, Any]]:
        """解析 SSE 事件流，yield 每个 JSON chunk。"""
        buffer = ""
        async for raw_bytes in response.aiter_bytes():
            buffer += raw_bytes.decode("utf-8", errors="replace")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()

                if not line:
                    continue

                if not line.startswith("data:"):
                    continue

                payload = line[5:].strip()

                if not payload:
                    continue

                if payload == "[DONE]":
                    return

                try:
                    chunk: dict[str, Any] = json.loads(payload)
                    yield chunk
                except json.JSONDecodeError:
                    logger.debug("Failed to parse SSE line: %s", line[:100])
                    continue

    # ------------------------------------------------------------------
    # 内部 — 错误处理
    # ------------------------------------------------------------------

    def _check_enabled(self) -> None:
        if not self._enabled:
            raise StepFunError("StepFun provider is disabled in model.json")

    def _check_auth(self) -> None:
        if not self._api_key:
            raise StepFunAuthError(
                "STEPFUN_API_KEY environment variable is not set"
            )

    def _make_api_error(self, response: httpx.Response) -> StepFunAPIError:
        try:
            body = response.json()
            message = (
                body.get("error", {})
                .get("message", response.text)
                if isinstance(body, dict)
                else response.text
            )
        except Exception:
            body = None
            message = response.text
        return StepFunAPIError(response.status_code, message, body)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()
