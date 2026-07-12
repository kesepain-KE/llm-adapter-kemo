# Kemo LLM Adapter — 新厂商接入指南

本文档面向 AI Agent，定义完整的 Provider 注册流程。**请严格按步骤执行，不要跳步。**

---

## 目录

- [Step 0 — 收集厂商信息](#step-0--收集厂商信息)
- [Step 1 — 最小化连通测试](#step-1--最小化连通测试)
- [Step 2 — 拉取并筛选模型](#step-2--拉取并筛选模型)
- [Step 2.5 — 读取厂商 API 文档](#step-25--读取厂商-api-文档)
- [Step 3 — 生成 Provider 样板](#step-3--生成-provider-样板)
- [Step 4 — 编写适配模块](#step-4--编写适配模块)
- [Step 5 — 注册到全局配置](#step-5--注册到全局配置)
- [Step 5.5 — Core 自检验证](#step-55--core-自检验证)
- [Step 6 — 批量测试并标注标签](#step-6--批量测试并标注标签)
- [Step 7 — 告知用户注册成功](#step-7--告知用户注册成功)
- [附录 A — 异常恢复与回滚](#附录-a--异常恢复与回滚)
- [附录 B — 完整文件清单](#附录-b--完整文件清单)
- [附录 C — 快速参考](#附录-c--快速参考)

---

## Step 0 — 收集厂商信息

动手前先确认以下信息。**这一步 AI Agent 独立完成，不允许问用户。**

### 自检清单

| 信息 | 来源 | 要求 |
|------|------|------|
| `name` | 用户给出的厂商名 | 作为目录名，纯小写 + 短横线，如 `mimo` |
| `base_url` | 用户提供 / 厂商 API 文档 | 如 `https://api.mimo.com` |
| `api_key_env` | 用户提供 | 环境变量名，如 `MIMO_API_KEY` |
| `api_key` | 用户提供 | 真实密钥，仅用于测试，**不写入代码** |
| 模型列表 | `GET /v1/models` 端点或文档 | 如 `mimo-v4-flash`, `mimo-v4-pro` |
| 聊天端点 | API 文档 | 通常 `POST /chat/completions` |
| 流式格式 | API 文档 | SSE 标准 / 变种 |
| 流式 usage | API 文档 / 实测 | 是否支持 `stream_options.include_usage=true` 或等价参数 |
| 认证方式 | API 文档 | Bearer token / API Key Header |
| 是否 OpenAI-compatible | 自行判断 | 是→chat.py 基本不用改；否→需映射 |
| 其他能力 | API 文档 | STT? TTS? 文生图? 嵌入? 重排? |

### 关键判断

- **OpenAI-compatible**: 请求/响应格式与 OpenAI 一致 → chat.py 几乎不需修改
- **非标准格式**: base_url 不同 / 参数名不同 / 认证方式不同 → 需要配置请求体映射

---

## Step 1 — 最小化连通测试

**拿到用户的 key 和 base_url 后，先做连通性测试，确认 API 有效。**

### 1.1 直接 curl 测试

```bash
# 替换为真实值
set PROVIDER_API_KEY=sk-xxx
set PROVIDER_BASE_URL=https://api.example.com

# 测试 chat 连通性
curl -X POST "%PROVIDER_BASE_URL%/chat/completions" ^
  -H "Authorization: Bearer %PROVIDER_API_KEY%" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"模型名\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"max_tokens\":50}"
```

### 1.2 测试判断

| 结果 | 处理 |
|------|------|
| `200 OK` + 有效响应 | ✅ API 有效，进入下一步 |
| `401 Unauthorized` | ❌ key 无效或格式错误，告知用户 |
| `404 Not Found` | ❌ base_url 或端点路径错误，核对文档 |
| `429 Too Many Requests` | ❌ 限流，告知用户稍后重试 |
| 其他错误 | 读取响应 body 错误信息，确认原因后告知用户 |

### 1.3 告知用户

```
连通性测试通过 ✅ API 有效，响应正常。
厂商: {name}
模型: 已确认 {模型数量} 个模型可访问
```

---

## Step 2 — 拉取并筛选模型

### 2.1 拉取模型列表

```bash
curl -H "Authorization: Bearer %PROVIDER_API_KEY%" "%PROVIDER_BASE_URL%/models"
```

如果厂商没有 `/models` 端点，从 API 文档收集模型列表。

### 2.2 整理模型清单

将返回的模型（或用户指定的模型）按实际名称整理：

```
{厂商名}:
  - {vendor_model_1} – 描述（如 快速推理 / 语音合成 / 文生图）
  - {vendor_model_2} – 描述
  - ...
```

### 2.3 询问用户

> 拉取到以下模型，请告诉我需要接入哪些：
>
> 1. `mimo-v4-flash` — 快速聊天
> 2. `mimo-v4-pro` — 深度推理
> 3. `mimo-audio-tts` — 语音合成
> 4. `mimo-image-gen` — 图片生成
>
> 回复序号或模型名，如「1,2,3」或「全部」

---

## Step 2.5 — 读取厂商 API 文档

用户确认模型后，在写任何代码之前，**先完整阅读厂商 API 文档的相关章节**，确认以下细节：

### 必读章节

```
□ 聊天端点请求/响应格式
  → 字段名是否与 OpenAI 一致？(model/messages/temperature/max_tokens...)
  → tools / tool_choice 是否支持？格式如何？
  → response_format (json_object) 是否支持？

□ 流式 SSE 格式
  → 每个 data: 行是否标准 JSON？
  → 末尾是否是 data: [DONE]？
  → 是否支持 stream_options: {include_usage: true}？
  → 如果不支持，是否有其他接口可获取真实 usage？否则只能走 prompt 估算，需在 explain.md 说明

□ 认证方式
  → Bearer token / API-Key Header / 其他？
  → 环境变量名确认

□ 错误响应格式
  → HTTP status code + error body 结构

□ 其他能力端点
  → TTS / ASR / 文生图 / 嵌入 → 请求/响应格式
```

### 读完后确认

| 如果厂商... | 则... |
|-------------|-------|
| 完全 OpenAI-compatible | chat.py 几乎不用改，只改 base_url 和模型名 |
| 参数名不同（如 `max_output_tokens`） | 改 `_build_request_body()` 做参数映射 |
| 认证方式非 Bearer | 改 `_build_headers()` |
| SSE 格式变种 | 改 `_parse_sse()` |
| 不支持流式 | `invoke_stream()` 抛 `NotImplementedError` |
| 不支持 tools | `model.json` 中设 `supports_tools: false` |
| 不支持 JSON mode | `model.json` 中设 `supports_json_output: false` |

---

## Step 3 — 生成 Provider 样板

用户确认模型后，创建 Provider 目录结构。

### 3.1 创建目录

```bash
mkdir provider\{name}\
```

```
provider/{name}/
├── model.json       # 厂商元信息（必填）
├── __init__.py      # 导出工厂 + 类（必填）
├── chat.py          # 聊天适配器（聊天模型必填）
├── token_count.py   # Token 统计（聊天模型必填）
├── audio.py         # 音频适配器（按需）
├── image.py         # 图像适配器（按需）
├── embedding.py     # 嵌入适配器（按需）
├── rerank.py        # 重排适配器（按需）
└── video.py         # 视频适配器（按需）
```

### 3.2 检查依赖

如果新厂商需要额外 Python 依赖（如自定义 SDK），必须先更新 `requirements.txt`：

```bash
# 追加到 requirements.txt
# 或安装后 pip freeze > requirements.txt
```

**规则：** 尽量用 `httpx` 直调 REST API，避免引入厂商 SDK 增加维护负担。

### 3.3 编写 model.json

这是最核心的配置文件，registry.py 自动读取。**不要直接复制 deepseek，用以下模板：**

```json
{
  "provider": "{name}",
  "enabled": true,
  "base_url": "{base_url}",
  "api_key_env": "{NAME_UPPER}_API_KEY",
  "modules": {
    "chat": "chat",
    "token_count": "token_count"
  },
  "models": {
    "{vendor_model_1}": {
      "capabilities": ["chat"],
      "vendor_model": "{vendor_model_1}",
      "endpoint": "/v1/chat/completions",
      "input": ["text"],
      "output": ["text"],
      "supports_stream": true,
      "supports_tools": true,
      "supports_json_output": true,
      "supports_thinking": false,
      "supports_reasoning": false
    }
  }
}
```

**字段说明：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `provider` | ✅ | 厂商名，与目录名一致 |
| `enabled` | ✅ | `true` / `false` |
| `base_url` | ✅ | API base URL（不带末尾 `/`） |
| `api_key_env` | ✅ | 环境变量名，从 `os.environ` 读密钥 |
| `modules` | ✅ | capability → 文件名映射 |
| `models` | ✅ | 此厂商支持的模型列表 |
| `models.*.capabilities` | ✅ | 能力数组，如 `["chat"]`, `["audio.tts"]`, `["chat", "vision.image"]` |
| `models.*.vendor_model` | ✅ | 传给厂商 API 的 model 参数值 |
| `models.*.endpoint` | ✅ | 此模型的 API 端点路径 |
| `models.*.supports_stream` | | 是否支持流式 |
| `models.*.supports_tools` | | 是否支持 function calling |
| `models.*.supports_json_output` | | 是否支持 JSON mode |
| `models.*.supports_thinking` | | 是否支持 thinking/reasoning |
| `models.*.supports_reasoning` | | 是否支持 `reasoning_effort` 参数 |
| `models.*.modalities` | | 多模态类型，如 `["text", "image", "video"]` |

> **关于多模态视觉：** vision 能力走 chat 通道，不需要单独的 capability 模块。只要厂商支持 content 数组格式中的 `image_url` 类型，模型声明 `capabilities: ["chat", "vision.image"]` 即可。

### 3.4 编写 __init__.py

```python
"""
{Name} provider 包入口。

对外暴露：
- {Name}Chat          —— 聊天适配器
- {Name}TokenCount    —— Token 统计器
- create_chat / create_token_count —— 工厂函数
"""

from __future__ import annotations

from .chat import {Name}Chat
from .token_count import {Name}TokenCount

__all__ = [
    "{Name}Chat",
    "{Name}TokenCount",
    "create_chat",
    "create_token_count",
]


def create_chat(config: dict | None = None) -> {Name}Chat:
    return {Name}Chat(config=config)


def create_token_count(config: dict | None = None) -> {Name}TokenCount:
    return {Name}TokenCount()
```

**命名约定：** `{PascalProvider}` + `{PascalCapability}`

| Provider 名 | Pascal 形式 | chat 类名 | token_count 类名 |
|-------------|-------------|-----------|------------------|
| `deepseek` | `DeepSeek` | `DeepSeekChat` | `DeepSeekTokenCount` |
| `stepfun` | `Stepfun` | `StepfunChat` | `StepfunTokenCount` |
| `mimo` | `Mimo` | `MimoChat` | `MimoTokenCount` |

---

## Step 4 — 编写适配模块

### 4.1 chat.py 适配器（必须）

**必须保留的公开接口：**

```python
class {Name}Chat:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._base_url = cfg.get("base_url", "").rstrip("/")
        env_key = cfg.get("api_key_env", "{NAME_UPPER}_API_KEY")
        self._api_key = os.environ.get(env_key, "")
        # ⚠️ 超时按实际需要调整。非流式大 payload 请求（如子代理计划生成）
        # 可能超过 120s，建议设为 600.0 以避免 ReadTimeout
        self._client = httpx.AsyncClient(timeout=600.0)

    async def invoke(self, request: dict) -> dict:
        """非流式。request/response 格式均为 OpenAI-compatible。"""
        ...

    async def invoke_stream(self, request: dict) -> AsyncIterator[dict]:
        """流式。yield 的每个 chunk 为 OpenAI-compatible。"""
        ...
```

**按需改写的方法：**

| 方法 | 职责 | 何时改 |
|------|------|--------|
| `_build_request_body()` | OpenAI 请求 → 厂商请求体 | 厂商不是标准 OpenAI 格式时 |
| `_build_headers()` | 认证头 | 认证方式不是 Bearer 时 |
| `_normalize_response()` | 厂商响应 → OpenAI 响应 | 字段名不同时 |
| `_normalize_stream_chunk()` | SSE chunk → OpenAI chunk | SSE 字段不同时 |
| `_parse_sse()` | SSE 字节流 → JSON chunk | SSE 不是标准格式时 |

**请求体参数映射参考：**

```
OpenAI 标准             厂商（按需映射）
─────────────────────   ─────────────────────
temperature             temperature / top_p
max_tokens              max_tokens / max_output_tokens
stop                    stop / stop_sequences
tools                   tools / functions
tool_choice             tool_choice
response_format         response_format (json_object)
stream_options          stream_options
user                    user / user_id

非标准扩展：
reasoning_effort        reasoning_effort (low/medium/high)
thinking                thinking ({"type": "enabled"})
```

**响应归一化（非流式）：**

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "{vendor_model}",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "..."},
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

**响应归一化（流式 chunk）：**

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion.chunk",
  "created": 1234567890,
  "model": "{vendor_model}",
  "choices": [{
    "index": 0,
    "delta": {"role": "assistant", "content": "逐字"},
    "finish_reason": null
  }],
  "usage": null
}
```

**⚠️ 关键规则：**
- 非流式响应**必须**有 `usage` 字段
- 流式请求必须在 `_build_request_body()` 或 `invoke_stream()` 中强制打开 usage，例如合并为 `{"include_usage": true}`；不能让客户端传 `false` 覆盖
- 流式最后一个 chunk **应**有 `usage` 字段（通过 `stream_options: {include_usage: true}` 实现）。如果厂商确实不支持，服务层会用 `token_count.count(request)` 做低精度 prompt 估算，completion/cache/reasoning 不准
- `choices[].delta` 第 1 个 chunk 的 role 应为 `"assistant"`
- 末尾 chunk 的 finish_reason 应为 `"stop"`，delta content 可为空
- `invoke_stream()` 不负责写日志；服务层会捕获最后一个带 `usage` 的 chunk 入库并扣配额

### 4.2 token_count.py 适配器（必须）

```python
"""
{Name} token 统计模块。
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


class {Name}TokenCount:
    @staticmethod
    def normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
        """归一化 API 响应的 usage → 统一格式。"""
        result: dict[str, Any] = dict(UNIFIED_USAGE_TEMPLATE)
        if not usage:
            return result
        result["prompt_tokens"] = usage.get("prompt_tokens", 0)
        result["completion_tokens"] = usage.get("completion_tokens", 0)
        result["total_tokens"] = usage.get("total_tokens", 0)

        # 兼容两类格式：
        # 1) 厂商原始嵌套字段，如 prompt_tokens_details.cached_tokens
        # 2) chat.py 已经扁平化后的 prompt_cache_hit_tokens / reasoning_tokens
        cached = usage.get("prompt_cache_hit_tokens", usage.get("cached_tokens", 0))
        prompt_details = usage.get("prompt_tokens_details", {})
        if isinstance(prompt_details, dict):
            cached = prompt_details.get("cached_tokens", cached)
        result["prompt_cache_hit_tokens"] = cached
        result["prompt_cache_miss_tokens"] = usage.get(
            "prompt_cache_miss_tokens",
            max(0, result["prompt_tokens"] - cached),
        )

        reasoning = usage.get("reasoning_tokens", usage.get("thinking_tokens", 0))
        completion_details = usage.get("completion_tokens_details", {})
        if isinstance(completion_details, dict):
            reasoning = completion_details.get("reasoning_tokens", reasoning)
        result["reasoning_tokens"] = reasoning
        return result

    @staticmethod
    def estimate_tokens(messages: list[dict[str, Any]], model: str | None = None) -> int:
        """预估消息列表的 token 数（离线）。"""
        return _estimate_tokens(messages, model)

    @staticmethod
    def count(request: dict[str, Any]) -> dict[str, Any]:
        usage = request.get("usage")
        if usage:
            return {Name}TokenCount.normalize_usage(usage)
        estimated = {Name}TokenCount.estimate_tokens(
            request.get("messages", []), request.get("model")
        )
        return {**UNIFIED_USAGE_TEMPLATE, "total_tokens": estimated, "prompt_tokens": estimated}
```

**两种需要修改的情况：**
1. **厂商 usage 字段名不一致** → 修改 `normalize_usage()` 的字段映射
2. **厂商有公开 tokenizer** → 修改 `estimate_tokens()` 使用该编码
3. **厂商把缓存/推理 token 放在嵌套 details 中** → 同时兼容嵌套字段和扁平字段，避免二次归一化时归零

| 统一字段 | 常见别名 |
|----------|----------|
| `prompt_tokens` | `input_tokens`, `prompt_length` |
| `completion_tokens` | `output_tokens`, `completion_length` |
| `total_tokens` | `total`, `sum` |
| `reasoning_tokens` | `thinking_tokens`, `reason_tokens` |
| `prompt_cache_hit_tokens` | `cached_tokens`, `prompt_tokens_details.cached_tokens` |
| `prompt_cache_miss_tokens` | `uncached_tokens`, `prompt_tokens - cached_tokens` |

### 4.3 audio.py — TTS + ASR 骨架（按需）

```python
"""
{Name} audio 适配器。
"""

import os
from typing import Any


class {Name}Audio:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._base_url = cfg.get("base_url", "").rstrip("/")
        env_key = cfg.get("api_key_env", "{NAME_UPPER}_API_KEY")
        self._api_key = os.environ.get(env_key, "")

    async def speech(self, request: dict[str, Any]) -> bytes:
        """文本转语音 (TTS)。
        
        参数 request: OpenAI-compatible 格式
            model: str
            input: str
            voice: str (可选)
            response_format: str (可选, mp3/opus/aac/flac)
            speed: float (可选)
        返回: 音频 bytes
        """
        # 1. 映射请求参数为厂商格式
        # 2. POST 到厂商 TTS 端点
        # 3. 返回音频二进制
        raise NotImplementedError("TTS not yet implemented")

    async def transcribe(self, request: dict[str, Any]) -> dict[str, Any]:
        """语音转文字 (ASR)。
        
        参数 request: OpenAI-compatible 格式
            model: str
            file: 音频文件 (multipart)
            language: str (可选)
            response_format: str (可选)
        返回: dict
            text: str
        """
        # 1. 构造 multipart 请求
        # 2. POST 到厂商 ASR 端点
        # 3. 归一化响应
        raise NotImplementedError("ASR not yet implemented")


def create_audio(config=None):
    return {Name}Audio(config=config)
```

### 4.4 image.py — 文生图 + 图生图骨架（按需）

```python
"""
{Name} image 适配器。
"""

import os
from typing import Any


class {Name}Image:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._base_url = cfg.get("base_url", "").rstrip("/")
        env_key = cfg.get("api_key_env", "{NAME_UPPER}_API_KEY")
        self._api_key = os.environ.get(env_key, "")

    async def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        """文生图。
        
        参数 request: OpenAI-compatible 格式
            model: str
            prompt: str
            n: int (可选, 生成数量)
            size: str (可选, 如 1024x1024)
            response_format: str (可选, url/b64_json)
        返回: dict
            created: int
            data: list[dict] — [{url: str} 或 {b64_json: str}]
        """
        # 1. 映射参数为厂商格式
        # 2. POST 到厂商图像生成端点
        # 3. 归一化响应
        raise NotImplementedError("Image generation not yet implemented")

    async def edit(self, request: dict[str, Any]) -> dict[str, Any]:
        """图生图/图像编辑。
        
        参数 request: OpenAI-compatible 格式
            model: str
            image: 原图
            prompt: str
            mask: 蒙版 (可选)
            response_format: str (可选)
        返回: dict (同 generate)
        """
        # 1. 构造 multipart 请求
        # 2. POST 到厂商图生图端点
        # 3. 归一化响应
        raise NotImplementedError("Image edit not yet implemented")


def create_image(config=None):
    return {Name}Image(config=config)
```

### 4.5 embedding.py / rerank.py / video.py — 骨架（按需）

```python
"""{Name} embedding 适配器。"""

import os
from typing import Any


class {Name}Embedding:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._base_url = cfg.get("base_url", "").rstrip("/")
        env_key = cfg.get("api_key_env", "{NAME_UPPER}_API_KEY")
        self._api_key = os.environ.get(env_key, "")

    async def embed(self, request: dict[str, Any]) -> dict[str, Any]:
        """文本嵌入。
        
        参数 request: OpenAI-compatible 格式
            model: str
            input: str | list[str]
        返回: dict
            object: str
            data: list[dict] — [{object, index, embedding}]
            model: str
            usage: dict
        """
        # 1. POST 到厂商嵌入端点
        # 2. 归一化响应
        raise NotImplementedError("Embedding not yet implemented")


def create_embedding(config=None):
    return {Name}Embedding(config=config)
```

```python
"""{Name} rerank 适配器。"""

import os
from typing import Any


class {Name}Rerank:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._base_url = cfg.get("base_url", "").rstrip("/")
        env_key = cfg.get("api_key_env", "{NAME_UPPER}_API_KEY")
        self._api_key = os.environ.get(env_key, "")

    async def rerank(self, request: dict[str, Any]) -> dict[str, Any]:
        """文档重排。"""
        raise NotImplementedError("Rerank not yet implemented")


def create_rerank(config=None):
    return {Name}Rerank(config=config)
```

```python
"""{Name} video 适配器。"""

import os
from typing import Any


class {Name}Video:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._base_url = cfg.get("base_url", "").rstrip("/")
        env_key = cfg.get("api_key_env", "{NAME_UPPER}_API_KEY")
        self._api_key = os.environ.get(env_key, "")


def create_video(config=None):
    return {Name}Video(config=config)
```

均按 `{Name}{Capability}` 类名 + `create_{capability}` 工厂函数命名。

---

## Step 5 — 注册到全局配置

共需修改 **4 个文件**：

### Step 5.1 — config/config.json：启用 Provider

```json
{
  "providers": {
    "{name}": { "enabled": true }
  }
}
```

key **必须**与 `provider/<目录名>` 一致。

### Step 5.2 — config/models.json：注册模型

```json
{
  "{name}-{vendor_model_1}": {
    "provider": "{name}",
    "model": "{vendor_model_1}",
    "capabilities": ["chat"],
    "endpoint": "/v1/chat/completions",
    "enabled": true,
    "visible": true
  },
  "{name}-{vendor_model_2}": {
    "provider": "{name}",
    "model": "{vendor_model_2}",
    "capabilities": ["audio.tts"],
    "endpoint": "/v1/audio/speech",
    "enabled": true,
    "visible": true
  }
}
```

**命名规则：** `{provider}-{vendor_model}`，用 `-` 连接。

### Step 5.3 — config/api_keys.json：给密钥添加模型权限

```json
{
  "keys": {
    "sk-your-key": {
      "models": ["{name}-{vendor_model_1}", "{name}-{vendor_model_2}"]
    }
  }
}
```

### Step 5.4 — provider.env：添加密钥

```bash
# 追加到 provider.env
{NAME_UPPER}_API_KEY=your-real-api-key
{NAME_UPPER}_BASE_URL={base_url}
```

环境变量名**必须**与 `model.json` 的 `api_key_env` 一致。

### 热加载规则

| 文件 | 修改后需重启 |
|------|-------------|
| `config/config.json` | ❌ 不用 |
| `config/models.json` | ❌ 不用 |
| `config/api_keys.json` | ❌ 不用 |
| `provider/{name}/model.json` | ✅ **必须重启** |
| `provider.env` | ✅ **必须重启** |
| `provider/{name}/*.py` | ✅ **必须重启** |

---

## Step 5.5 — Core 自检验证

**在重启服务器之前**，先通过 Python 验证代码和配置是否正确。这能提前捕获 ImportError、注册失败等错误，避免直接 HTTP 测试时爆 500。

```bash
python -c "
import sys; sys.path.insert(0, '.')
from core import bootstrap

ctx = bootstrap('.')
print('Providers:', ctx.registry.list_providers())
print('Capabilities:', ctx.registry.list_capabilities('{name}'))
print('Models:', ctx.registry.list_models('{name}'))
print('Route:', ctx.router.resolve('{name}-{vendor_model_1}'))
print('Keys:', len(ctx.auth.list_keys()))
"
```

### 常见自检错误

| 报错 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: No module named 'provider.{name}'` | `provider/{name}/__init__.py` 不存在或语法错误 | 检查文件是否存在、Python 语法 |
| `ModuleNotFoundError: No module named 'provider.{name}.chat'` | `chat.py` 不存在或 `model.json` 的 modules 声明了但文件缺失 | 检查文件名和 modules 映射 |
| `AttributeError: module '...' has no attribute 'create_chat'` | `__init__.py` 未导出工厂函数 | 检查工厂函数命名 |
| `RouterError: unknown model` | `config/models.json` 未注册 | 检查 Step 5.2 |
| `ImportError`（内部行） | 代码有语法错误或缺失 `httpx` 等依赖 | 检查 `requirements.txt` |

**通过自检后再重启，否则回头修代码。**

---

## Step 6 — 批量测试并标注标签

### 6.1 重启服务器

```bash
# 如果正在运行，Ctrl+C 后重新启动
python server.py --port 8741
```

### 6.2 自检注册情况

```bash
# 健康检查，确认 provider 已加载
curl http://127.0.0.1:8741/api/health

# 查看可用模型
curl -H "Authorization: Bearer sk-your-key" http://127.0.0.1:8741/v1/models

# 列出所有 provider
curl http://127.0.0.1:8741/api/providers
```

### 6.3 逐模型测试

**每个模型测试其声明的全部 capability，测试结果记录为标签：**

| Capability | 测试方法 | 成功标签 | 失败标签 |
|-----------|----------|----------|----------|
| `chat` (非流式) | `POST /v1/chat/completions` `stream:false` | `✅ chat` | `❌ chat` |
| `chat` (流式) | `POST /v1/chat/completions` `stream:true`，并检查 `/api/logs` 中 usage 入库 | `✅ stream` | `❌ stream` |
| `vision.image` | 多模态消息含 `image_url` | `✅ vision` | `❌ vision` |
| `audio.tts` | `POST /v1/audio/speech` | `✅ tts` | `❌ tts` |
| `audio.asr` | `POST /v1/audio/transcriptions` | `✅ asr` | `❌ asr` |
| `image.generation` | `POST /v1/images/generations` | `✅ image` | `❌ image` |
| `image.edit` | `POST /v1/images/edits` | `✅ edit` | `❌ edit` |
| `embedding` | `POST /v1/embeddings` | `✅ embedding` | `❌ embedding` |
| `rerank` | `POST /v1/rerank` | `✅ rerank` | `❌ rerank` |
| `video.*` | `POST /v1/videos/generations` | `✅ video` | `❌ video` |

### 6.4 测试命令示例

```bash
# 非流式聊天
curl -X POST http://127.0.0.1:8741/v1/chat/completions ^
  -H "Authorization: Bearer sk-your-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"{name}-{vendor_model}\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"max_tokens\":50}"

# 流式聊天
curl -X POST http://127.0.0.1:8741/v1/chat/completions ^
  -H "Authorization: Bearer sk-your-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"{name}-{vendor_model}\",\"messages\":[{\"role\":\"user\",\"content\":\"数到3\"}],\"stream\":true}"

# 验证统计入库（确认上面的非流式/流式请求都有 total_tokens）
curl -H "Authorization: Bearer <admin-session-token>" ^
  "http://127.0.0.1:8741/api/logs?limit=10"

# TTS
curl -X POST http://127.0.0.1:8741/v1/audio/speech ^
  -H "Authorization: Bearer sk-your-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"{name}-{audio_model}\",\"input\":\"你好\"}" ^
  --output test.mp3

# 文生图
curl -X POST http://127.0.0.1:8741/v1/images/generations ^
  -H "Authorization: Bearer sk-your-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"{name}-{img_model}\",\"prompt\":\"一只猫\"}"
```

### 6.5 测试超时处理

| 情况 | 处理 |
|------|------|
| curl 卡住超过 30 秒无响应 | `Ctrl+C` 中断，标注 ❌ timeout |
| 返回 `502 Provider error` | 密钥无效/余额不足/网络不通 |
| 返回 `500 Internal Server Error` | 适配器代码问题，回 Step 4 排查 |

### 6.6 模型标签整理示例

```
{name}-{vendor_model_1} — 【chat ✅ stream ✅ vision ❌】快速聊天
{name}-{vendor_model_2} — 【tts ✅】语音合成
{name}-{vendor_model_3} — 【image ✅】文生图
```

---

## Step 7 — 告知用户注册成功

### 汇报模板

```
✅ 厂商接入完成：{name}

已注册以下模型：
{m1} — 【chat ✅ stream ✅】聊天模型
{m2} — 【tts ✅】语音合成
{m3} — 【image ✅】文生图

配置摘要：
- 环境变量: {NAME_UPPER}_API_KEY（已写入 provider.env）
- 暴露模型名: {name}-{model} 格式
- 测试密钥: sk-xxx（已授权）
- API 端点: http://127.0.0.1:8741/v1/chat/completions（标准 OpenAI 格式）

未通过的测试已标注 ❌，如需排查请在对话中指明模型名。
```

---

## 附录 A — 异常恢复与回滚

### A.1 自检失败（Step 5.5 报错）

1. 读报错信息定位问题文件
2. 常见修复：
   - `ModuleNotFoundError` → 检查文件名、`modules` 声明、`__init__.py`
   - `SyntaxError` → Python 语法错误，修正后重试
   - `RouterError: unknown model` → 检查 `config/models.json`
3. 修完后重新执行 Step 5.5

### A.2 重启后 HTTP 测试全挂

```bash
# 1. 看服务日志是否有报错
python server.py --port 8741  # 前台运行，观察 stdout

# 2. 确认 provider 是否被加载
curl http://127.0.0.1:8741/api/providers

# 3. 如果还是不行 → 回滚配置
```

### A.3 回滚操作

```bash
# 回滚 provider 目录
rm -rf provider/{name}/

# 从 config.json 移除 provider 条目
# 从 models.json 移除所有 {name}-* 条目
# 从 api_keys.json 移除已授权的模型
# 从 provider.env 移除 {NAME_UPPER}_API_KEY

# 重启
python server.py
```

### A.4 需要人工介入的情况

| 场景 | 处理 |
|------|------|
| 厂商 API 文档不清楚 | 描述看到的内容，问用户确认 |
| 密钥多次验证失败 | 告知用户，请求重新提供 |
| 自定义认证流程复杂（OAuth2） | 描述需求和方案，让用户决策 |
| 适配器代码需要复杂调试 | 向用户说明问题，提供调试日志 |

---

## 附录 B — 完整文件清单

接入完成后确认以下文件全部就位：

### Provider 目录

```
provider/{name}/
├── model.json        ← base_url, api_key_env, modules, models
├── __init__.py       ← 导出全部类 + 工厂函数
├── chat.py           ← invoke + invoke_stream
├── token_count.py    ← normalize_usage + estimate_tokens
├── audio.py          ← 按需
├── image.py          ← 按需
├── embedding.py      ← 按需
├── rerank.py         ← 按需
└── video.py          ← 按需
```

### 全局配置

```
config/config.json    ← providers.{name}.enabled = true
config/models.json    ← {name}-{vendor_model} 条目
config/api_keys.json  ← 密钥已授权新模型
provider.env           ← 已添加 {NAME_UPPER}_API_KEY
```

---

## 附录 C — 快速参考

### Registry 发现规则

1. `core/registry.py` 扫描 `provider/*/model.json` 的 `modules` 字段
2. 先找 `__init__.py` 的工厂函数 → 再找 `{module}.py` 的工厂 → 最后用类名匹配
3. 匹配到后注入 `model.json` 配置并实例化

### 类名与工厂命名

| 规则 | 示例（provider=minimax, capability=audio） |
|------|---------------------------------------------|
| 类名 | `{PascalProvider}{PascalCapability}` → `MinimaxAudio` |
| 工厂名 | `create_{capability}` → `create_audio` |
| 文件名 | `{capability}.py` → `audio.py` |
| model.json modules key | `"audio": "audio"` |

**不要改这些命名** — registry 靠它们自动发现模块。

### 模型命名

```
{provider}-{vendor_model}
示例: deepseek-deepseek-v4-flash
     stepfun-step-3.7-flash
     mimo-mimo-v4-pro
```

### 端口默认值

```bash
python server.py            # 默认 127.0.0.1:8741
python server.py --port 8741 --host 0.0.0.0  # 局域网可访问
```
