"""
生成新 provider 样板文件。

不会覆盖已有文件——只在新厂商初次接入时使用。

- chat / token_count → 完整带业务逻辑的样板（可直接改）
- audio / image / video / embedding / rerank → 最小骨架（agent 自己填）

用法::

    from add_diy.scaffold import scaffold
    scaffold("minimax", base_url="https://api.minimax.com",
             modules=["chat", "token_count", "audio", "image"])
"""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# 注册中心已知的标准 capability
# 与 core/registry.py 的 CAPABILITY_MODULE 保持同步
# ---------------------------------------------------------------------------
CAPABILITY_MODULE = {
    "chat":        "chat",
    "token_count": "token_count",
    "audio":       "audio",
    "image":       "image",
    "video":       "video",
    "embedding":   "embedding",
    "rerank":      "rerank",
}

# ---------------------------------------------------------------------------
# 通用骨架 — 用于 chat / token_count 之外的 capability
# ---------------------------------------------------------------------------
UNIVERSAL_SKELETON = '''"""
__PROVIDER_TITLE__ __CAPABILITY__ 适配器（骨架）。

agent 按厂商 API 文档填充具体逻辑。
注意：
  - 类名和工厂函数名不要改（registry 靠它们发现模块）
  - __init__(config) 接收 model.json 的完整内容
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class __PROVIDER_TITLE____PASCAL_CAP__:
    """__CAPABILITY__ 适配器。

    参数
    ----
    config : dict | None
        model.json 完整内容。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        # TODO: 从 cfg 读取 base_url / api_key_env 等
        self._enabled: bool = cfg.get("enabled", True)

    # TODO: agent 在此添加业务方法


def create___MODULE__(config: dict[str, Any] | None = None) -> __PROVIDER_TITLE____PASCAL_CAP__:
    """工厂函数 — registry 通过此函数创建实例。"""
    return __PROVIDER_TITLE____PASCAL_CAP__(config=config)
'''


# ===========================================================================
# chat / token_count — 完整样板（带参考代码）
# ===========================================================================

CHAT_TEMPLATE = '''"""
__PROVIDER_TITLE__ 聊天适配器。

样板——按厂商 API 文档修改以下方法：
  - _build_request_body : 映射参数到厂商请求格式
  - _build_headers      : 认证头 + Content-Type
  - _normalize_response : 厂商响应 → OpenAI 兼容格式
  - _normalize_stream_chunk : SSE chunk → OpenAI 兼容格式
  - _parse_sse          : 如果厂商 SSE 格式不同，改这里

必须保留的公开接口：
  - invoke(request) → dict
  - invoke_stream(request) → AsyncIterator[dict]
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "__BASE_URL__"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class __PROVIDER_TITLE__Error(Exception):
    """API 通用错误。"""


class __PROVIDER_TITLE__AuthError(__PROVIDER_TITLE__Error):
    """API Key 缺失或无效。"""


class __PROVIDER_TITLE__APIError(__PROVIDER_TITLE__Error):
    """API 返回错误响应。"""

    def __init__(self, status_code: int, message: str, body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class __PROVIDER_TITLE__Chat:
    """__PROVIDER_TITLE__ 聊天适配器。"""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ):
        cfg = config or {}

        self._base_url: str = (
            cfg.get("base_url")
            or os.environ.get("__API_KEY_ENV_BASE_URL__")
            or DEFAULT_BASE_URL
        ).rstrip("/")

        self._api_key: str = (
            os.environ.get(cfg.get("api_key_env", "__API_KEY_ENV__")) or ""
        )

        self._enabled: bool = cfg.get("enabled", True)
        self._models: dict[str, dict[str, Any]] = cfg.get("models", {})

        self._client: httpx.AsyncClient = http_client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
        )

    # ------------------------------------------------------------------
    # 公开接口 — 不要改签名
    # ------------------------------------------------------------------

    async def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        """非流式聊天补全。"""
        self._check_enabled()
        self._check_auth()

        body = self._build_request_body(request)
        body["stream"] = False

        url = f"{self._base_url}/chat/completions"
        headers = self._build_headers()

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

        url = f"{self._base_url}/chat/completions"
        headers = self._build_headers()

        async with self._client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code != 200:
                raise self._make_api_error(resp)

            async for chunk in self._parse_sse(resp):
                yield self._normalize_stream_chunk(chunk)

    # ------------------------------------------------------------------
    # 内部 — 按厂商文档修改以下方法
    # ------------------------------------------------------------------

    def _build_request_body(self, request: dict[str, Any]) -> dict[str, Any]:
        """OpenAI 兼容请求 → 厂商请求体。"""
        body: dict[str, Any] = {
            "model": request.get("model", "__VENDOR_MODEL__"),
            "messages": request.get("messages", []),
        }

        for param in ("temperature", "top_p", "max_tokens", "stop"):
            if param in request:
                body[param] = request[param]

        # tools / tool_choice / response_format — 按厂商支持情况添加
        tools = request.get("tools")
        if tools:
            body["tools"] = tools

        return body

    def _build_headers(self) -> dict[str, str]:
        """构建 HTTP 请求头。"""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _normalize_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """厂商响应 → OpenAI 兼容格式。"""
        return {
            "id": data.get("id", ""),
            "object": "chat.completion",
            "created": data.get("created", int(time.time())),
            "model": data.get("model", "__VENDOR_MODEL__"),
            "choices": data.get("choices", []),
            "usage": data.get("usage"),
        }

    def _normalize_stream_chunk(self, chunk: dict[str, Any]) -> dict[str, Any]:
        """SSE chunk → OpenAI 兼容格式。"""
        return {
            "id": chunk.get("id", ""),
            "object": "chat.completion.chunk",
            "created": chunk.get("created", 0),
            "model": chunk.get("model", "__VENDOR_MODEL__"),
            "choices": chunk.get("choices", []),
            "usage": chunk.get("usage"),
        }

    async def _parse_sse(
        self, response: httpx.Response
    ) -> AsyncIterator[dict[str, Any]]:
        """解析 SSE 事件流。"""
        buffer = ""
        async for raw_bytes in response.aiter_bytes():
            buffer += raw_bytes.decode("utf-8", errors="replace")

            while "\\n" in buffer:
                line, buffer = buffer.split("\\n", 1)
                line = line.strip()

                if not line or not line.startswith("data:"):
                    continue

                payload = line[5:].strip()
                if not payload:
                    continue
                if payload == "[DONE]":
                    return

                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue

    # ------------------------------------------------------------------
    # 内部 — 通用（一般不用改）
    # ------------------------------------------------------------------

    def _check_enabled(self) -> None:
        if not self._enabled:
            raise __PROVIDER_TITLE__Error(
                "__PROVIDER_TITLE__ provider is disabled in model.json"
            )

    def _check_auth(self) -> None:
        if not self._api_key:
            raise __PROVIDER_TITLE__AuthError(
                "__API_KEY_ENV__ environment variable is not set"
            )

    def _make_api_error(self, response: httpx.Response) -> __PROVIDER_TITLE__APIError:
        try:
            body = response.json()
            message = (
                body.get("error", {}).get("message", response.text)
                if isinstance(body, dict)
                else response.text
            )
        except Exception:
            body = None
            message = response.text
        return __PROVIDER_TITLE__APIError(response.status_code, message, body)

    async def close(self) -> None:
        await self._client.aclose()
'''

TOKEN_COUNT_TEMPLATE = '''"""
__PROVIDER_TITLE__ token 统计模块。

如果厂商有官方的 usage 格式与 OpenAI 不同，改 normalize_usage。
如果厂商有公开 tokenizer，改 estimate_tokens 里的编码选择。
否则保留三层策略不变。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

UNIFIED_USAGE_TEMPLATE = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": 0,
    "reasoning_tokens": 0,
}


def normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    """厂商 usage → 统一格式。"""
    result: dict[str, Any] = dict(UNIFIED_USAGE_TEMPLATE)
    if not usage:
        return result

    result["prompt_tokens"] = usage.get("prompt_tokens", 0)
    result["completion_tokens"] = usage.get("completion_tokens", 0)
    result["total_tokens"] = usage.get("total_tokens", 0)

    cache = usage.get("prompt_cache_hit_tokens")
    if cache is not None:
        result["prompt_cache_hit_tokens"] = cache

    cache_miss = usage.get("prompt_cache_miss_tokens")
    if cache_miss is not None:
        result["prompt_cache_miss_tokens"] = cache_miss

    details = usage.get("completion_tokens_details", {})
    if isinstance(details, dict):
        result["reasoning_tokens"] = details.get("reasoning_tokens", 0)

    return result


def _load_tokenizer():
    """延迟加载 tiktoken。"""
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def estimate_tokens(
    messages: list[dict[str, Any]],
    model: str | None = None,
) -> int:
    """离线预估 token 数。"""
    text = _extract_text(messages)
    enc = _load_tokenizer()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return _rough_estimate(text)


def _extract_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return "\\n".join(parts)


def _rough_estimate(text: str) -> int:
    if not text:
        return 0
    cjk = latin = 0
    for ch in text:
        cp = ord(ch)
        if cp < 0x80:
            latin += 1
        elif (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0x3040 <= cp <= 0x30FF
            or 0xAC00 <= cp <= 0xD7AF
        ):
            cjk += 1
        else:
            latin += 1
    return max(int(cjk / 1.5 + latin / 4.0), 1)


class __PROVIDER_TITLE__TokenCount:
    """__PROVIDER_TITLE__ token 统计器。"""

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}

    @staticmethod
    def normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
        return normalize_usage(usage)

    @staticmethod
    def estimate_tokens(
        messages: list[dict[str, Any]],
        model: str | None = None,
    ) -> int:
        return estimate_tokens(messages, model)

    @staticmethod
    def count(request: dict[str, Any]) -> dict[str, Any]:
        usage = request.get("usage")
        if usage:
            return normalize_usage(usage)
        messages = request.get("messages", [])
        model = request.get("model")
        estimated = estimate_tokens(messages, model)
        return {
            **UNIFIED_USAGE_TEMPLATE,
            "total_tokens": estimated,
            "prompt_tokens": estimated,
            "completion_tokens": 0,
        }
'''


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _pascal_case(name: str) -> str:
    """snake_case/hyphen-case → PascalCase。"""
    name = name.replace("-", " ").replace("_", " ")
    return "".join(w.title() for w in name.split())


def _fill(template: str, **kwargs) -> str:
    """__KEY__ → value。"""
    result = template
    for key, val in kwargs.items():
        result = result.replace(f"__{key}__", str(val))
    return result


def _capability_class_suffix(capability: str) -> str:
    """capability → PascalCase 类名后缀。"""
    return _pascal_case(capability)


# ---------------------------------------------------------------------------
# 动态内容生成
# ---------------------------------------------------------------------------

def _build_model_json(
    provider: str,
    base_url: str,
    api_key_env: str,
    vendor_model: str,
    modules: list[str],
) -> str:
    """动态构建 model.json 内容。"""
    # modules 区
    modules_entries = []
    for m in modules:
        file_name = CAPABILITY_MODULE.get(m, m)
        modules_entries.append(f'    "{m}": "{file_name}"')

    return f"""{{
  "provider": "{provider}",
  "enabled": true,
  "base_url": "{base_url}",
  "api_key_env": "{api_key_env}",
  "modules": {{
{",".join(modules_entries)}
  }},
  "models": {{
    "{vendor_model}": {{
      "capability": "chat",
      "vendor_model": "{vendor_model}",
      "supports_stream": true,
      "supports_tools": false,
      "supports_json_output": false,
      "supports_thinking": false
    }}
  }}
}}
"""


def _build_init_py(
    provider_title: str,
    modules: list[str],
) -> str:
    """动态构建 __init__.py 内容。"""
    # --- import 行 ---
    imports: list[str] = []
    exports: list[str] = []
    factories: list[str] = []

    for m in modules:
        file_name = CAPABILITY_MODULE.get(m, m)
        pascal_cap = _pascal_case(m)
        class_name = f"{provider_title}{pascal_cap}"
        factory_name = f"create_{m}"

        imports.append(f"from .{file_name} import {class_name}")
        exports.append(f'    "{class_name}"')
        exports.append(f'    "{factory_name}"')

        factories.append(f"""
def {factory_name}(config: dict | None = None) -> {class_name}:
    return {class_name}(config=config)""")

    import_block = "\n".join(imports)
    export_block = ",\n".join(exports)
    factory_block = "".join(factories)

    return f'''"""
{provider_title} provider 包入口。

模块: {", ".join(modules)}
"""

from __future__ import annotations

{import_block}

__all__ = [
{export_block},
]
{factory_block}
'''


# ---------------------------------------------------------------------------
# 公开
# ---------------------------------------------------------------------------

def scaffold(
    provider: str,
    *,
    base_url: str = "https://api.example.com",
    vendor_model: str | None = None,
    api_key_env: str | None = None,
    modules: list[str] | None = None,
    project_root: str | Path = ".",
) -> dict[str, Path]:
    """生成新 provider 样板文件。**不覆盖已有文件。**

    参数
    ----
    provider : str
        厂商目录名，如 ``"minimax"``。
    base_url : str
        API base URL。
    vendor_model : str | None
        默认模型名。不传则用 provider 名。
    api_key_env : str | None
        密钥环境变量名。不传则自动推导。
    modules : list[str] | None
        要生成的模块 capability 名。
        默认 ``["chat", "token_count"]``。
        标准值: chat, token_count, audio, image, video, embedding, rerank

    project_root : str | Path
        项目根目录。

    返回
    ----
    dict[str, Path]
        已创建的文件路径。
    """
    if vendor_model is None:
        vendor_model = provider

    if api_key_env is None:
        api_key_env = f"{provider.upper().replace('-', '_')}_API_KEY"

    if modules is None:
        modules = ["chat", "token_count"]

    provider_title = _pascal_case(provider)
    api_key_env_base_url = f"{provider.upper().replace('-', '_')}_BASE_URL"

    replacements = {
        "PROVIDER": provider,
        "PROVIDER_TITLE": provider_title,
        "BASE_URL": base_url,
        "API_KEY_ENV": api_key_env,
        "API_KEY_ENV_BASE_URL": api_key_env_base_url,
        "VENDOR_MODEL": vendor_model,
    }

    root = Path(project_root)
    provider_dir = root / "provider" / provider
    provider_dir.mkdir(parents=True, exist_ok=True)

    created: dict[str, Path] = {}

    # ---- model.json ----
    model_json_path = provider_dir / "model.json"
    if not model_json_path.exists():
        content = _build_model_json(provider, base_url, api_key_env,
                                    vendor_model, modules)
        model_json_path.write_text(content, encoding="utf-8")
        created["model.json"] = model_json_path

    # ---- __init__.py ----
    init_py_path = provider_dir / "__init__.py"
    if not init_py_path.exists():
        content = _build_init_py(provider_title, modules)
        init_py_path.write_text(content, encoding="utf-8")
        created["__init__.py"] = init_py_path

    # ---- 各模块文件 ----
    for m in modules:
        file_name = CAPABILITY_MODULE.get(m, m)
        file_path = provider_dir / f"{file_name}.py"
        if file_path.exists():
            continue

        if m == "chat":
            content = _fill(CHAT_TEMPLATE, **replacements)
        elif m == "token_count":
            content = _fill(TOKEN_COUNT_TEMPLATE, **replacements)
        else:
            # 通用骨架
            pascal_cap = _pascal_case(m)
            content = _fill(UNIVERSAL_SKELETON,
                            PROVIDER_TITLE=provider_title,
                            CAPABILITY=m,
                            MODULE=file_name,
                            PASCAL_CAP=pascal_cap,
                            VENDOR_MODEL=vendor_model,
                            BASE_URL=base_url,
                            API_KEY_ENV=api_key_env,
                            API_KEY_ENV_BASE_URL=api_key_env_base_url,
                            )

        file_path.write_text(content, encoding="utf-8")
        created[f"{file_name}.py"] = file_path

    return created
