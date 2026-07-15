"""
DeepSeek 聊天适配器。

将统一格式的聊天请求转换为 DeepSeek API 调用，
处理 stream / non-stream、tool calls、thinking。

核心流程::

    request → _build_request_body → API 调用
           → _normalize_response → 统一格式响应

API 文档: https://api-docs.deepseek.com/zh-cn/api/create-chat-completion
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------

class DeepSeekError(Exception):
    """DeepSeek API 通用错误。"""


class DeepSeekAuthError(DeepSeekError):
    """API Key 缺失或无效。"""


class DeepSeekAPIError(DeepSeekError):
    """API 返回错误响应。"""

    def __init__(self, status_code: int, message: str, body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# ---------------------------------------------------------------------------
# 适配器
# ---------------------------------------------------------------------------

class DeepSeekChat:
    """DeepSeek 聊天适配器。

    用法::

        chat = DeepSeekChat(config=model_json)
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
        """初始化适配器。

        参数
        ----
        config : dict | None
            model.json 的内容。为 None 时使用默认 base_url。
        http_client : httpx.AsyncClient | None
            可注入外部 AsyncClient（测试/复用连接池）。
        """
        cfg = config or {}

        self._base_url: str = (
            cfg.get("base_url") or os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")

        self._api_key: str = (
            os.environ.get(cfg.get("api_key_env", "DEEPSEEK_API_KEY")) or ""
        )

        self._enabled: bool = cfg.get("enabled", True)

        # 模型配置（用于 vendor_model 映射等）
        self._models: dict[str, dict[str, Any]] = cfg.get("models", {})

        # HTTP 客户端
        self._client: httpx.AsyncClient = http_client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
        )

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        """非流式聊天补全。

        参数
        ----
        request : dict
            统一格式请求（OpenAI-compatible）。

        返回
        ----
        dict
            统一格式响应。
        """
        self._check_enabled()
        self._check_auth()

        body = self._build_request_body(request)
        body["stream"] = False

        url = f"{self._base_url}/chat/completions"
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
        """流式聊天补全。

        参数
        ----
        request : dict
            统一格式请求。

        Yields
        ------
        dict
            统一格式的流式 chunk（含 usage 的末 chunk）。
        """
        self._check_enabled()
        self._check_auth()

        body = self._build_request_body(request)
        body["stream"] = True

        # 在流式末尾返回 usage
        stream_options = body.get("stream_options")
        if not isinstance(stream_options, dict):
            stream_options = {}
        body["stream_options"] = {**stream_options, "include_usage": True}

        url = f"{self._base_url}/chat/completions"
        headers = self._build_headers()

        logger.debug("invoke_stream url=%s model=%s", url, body.get("model"))

        async with self._client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code != 200:
                await resp.aread()
                raise self._make_api_error(resp)

            async for chunk in self._parse_sse(resp):
                yield self._normalize_stream_chunk(chunk)

    # ------------------------------------------------------------------
    # 内部 — 请求构建
    # ------------------------------------------------------------------

    def _build_request_body(self, request: dict[str, Any]) -> dict[str, Any]:
        """构建 DeepSeek API 请求体，映射所有支持参数。"""
        body: dict[str, Any] = {
            "model": request.get("model", "deepseek-v4-flash"),
            "messages": request.get("messages", []),
        }

        # ---- 基础参数 ----
        for param in ("temperature", "top_p", "max_tokens", "stop"):
            if param in request:
                body[param] = request[param]

        # ---- user_id (DeepSeek 使用 user_id 而非 OpenAI 的 user) ----
        user_id = request.get("user_id") or request.get("user")
        if user_id is not None:
            body["user_id"] = user_id

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

        # ---- thinking (DeepSeek 扩展) ----
        thinking = request.get("thinking")
        if thinking is not None:
            body["thinking"] = thinking

        # ---- reasoning_effort ----
        reasoning_effort = request.get("reasoning_effort")
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort

        # ---- stream_options ----
        stream_options = request.get("stream_options")
        if stream_options is not None:
            body["stream_options"] = stream_options

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
        """将 DeepSeek API 响应归一化为统一格式 (OpenAI-compatible)。"""
        return {
            "id": data.get("id", ""),
            "object": data.get("object", "chat.completion"),
            "created": data.get("created", int(time.time())),
            "model": data.get("model", "deepseek-v4-flash"),
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
            "model": chunk.get("model", "deepseek-v4-flash"),
            "choices": chunk.get("choices", []),
            "usage": chunk.get("usage"),
        }

    # ------------------------------------------------------------------
    # 内部 — SSE 解析
    # ------------------------------------------------------------------

    async def _parse_sse(
        self, response: httpx.Response
    ) -> AsyncIterator[dict[str, Any]]:
        """解析 SSE 事件流，yield 每个 JSON chunk。

        SSE 格式::

            data: {...}\n
            data: {...}\n\n
            data: [DONE]\n\n
        """
        done_received = False
        async for line in response.aiter_lines():
            line = line.strip()

            if not line or not line.startswith("data:"):
                continue

            payload = line[5:].strip()
            if not payload:
                continue

            if payload == "[DONE]":
                done_received = True
                break

            try:
                chunk: dict[str, Any] = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise DeepSeekError(
                    f"DeepSeek stream returned malformed SSE data: {payload[:160]}"
                ) from exc

            if chunk.get("error"):
                error = chunk["error"]
                if isinstance(error, dict):
                    message = error.get("message") or error.get("detail") or str(error)
                else:
                    message = str(error)
                raise DeepSeekError(f"DeepSeek stream error: {message}")

            yield chunk

        if not done_received:
            raise DeepSeekError("DeepSeek stream closed before [DONE]")

    # ------------------------------------------------------------------
    # 内部 — 错误处理
    # ------------------------------------------------------------------

    def _check_enabled(self) -> None:
        """检查 provider 是否启用。"""
        if not self._enabled:
            raise DeepSeekError("DeepSeek provider is disabled in model.json")

    def _check_auth(self) -> None:
        """检查 API Key 是否配置。"""
        if not self._api_key:
            raise DeepSeekAuthError(
                "DEEPSEEK_API_KEY environment variable is not set"
            )

    def _make_api_error(self, response: httpx.Response) -> DeepSeekAPIError:
        """从 HTTP 错误响应构建异常。"""
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
        return DeepSeekAPIError(response.status_code, message, body)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """关闭 HTTP 客户端（仅当客户端由本实例创建时）。"""
        await self._client.aclose()
