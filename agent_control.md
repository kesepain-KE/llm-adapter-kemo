# Kemo LLM Adapter — Agent 接入新厂商说明书

当用户要求「接入 XXX 厂商」时，按本文档逐步操作。不要跳步。

---

## 1. 项目架构速览

```
config/
  config.json        ← provider 启停开关
  models.json        ← 暴露给用户的模型名 → provider+model 映射
  api_keys.json      ← API 密钥 + 模型白名单 + 配额
  global_prompt.md   ← 全局安全提示词（文本文件）

provider/<厂商名>/
  model.json         ← 厂商元信息: base_url, api_key_env, 模型列表, 能力标签
  __init__.py        ← 导出所有 capability 类 + create_* 工厂函数
  chat.py            ← 聊天适配器 (有完整样板)
  token_count.py     ← Token 统计 (有完整样板)
  audio.py           ← 音频适配器骨架（agent 自己填）
  image.py           ← 图像适配器骨架（agent 自己填）
  embedding.py       ← 嵌入适配器骨架（agent 自己填）
  ...                ← 其他 capability 同理，按需生成

core/                ← 编排层（一般不需要改）
  registry.py        ← 自动扫描 provider/*/model.json 加载模块
  router.py          ← 解析 models.json 暴露模型名
  auth.py            ← 密钥鉴权 + 模型白名单
  logger.py          ← 请求日志 (JSON Lines)
  usage.py           ← 用量统计 + 持久化

add_diy/             ← 工具包
  scaffold.py        ← 生成 provider/<name>/ 样板文件
  test.py            ← 最小连通测试
```

**核心约定：**
- `{provider}-{vendor_model}` 命名规则：用 `-` 连起来，如 `deepseek-deepseek-v4-flash`
- 各 provider 之间完全隔离，不互相 import
- 统一请求/响应格式均为 OpenAI-compatible

---

## 2. 注册机制 — 如何加新 capability

### 2.1 registry 发现规则

`core/registry.py` 按以下规则自动发现并加载模块：

1. 读 `provider/<name>/model.json` 的 `modules` 字段
2. 对每个 capability key，查找文件 `{module}.py`
3. 先调 `provider/<name>/__init__.py` 里的 `create_{module}(config)` 工厂
4. 找不到时，回退到 `provider/<name>/{module}.py` 里的 `create_{module}(config)` 工厂
5. 再找不到时，用类名匹配：`{ProviderPascal}{CapabilityPascal}`

**这意味着**：只要在 `model.json` 的 `modules` 里声明 capability，并在目录下放一个对应的 `.py` 文件（含类 + 工厂），registry 无需任何修改就能加载。

### 2.2 标准 capability 清单

| capability | 模块文件 | 用途 |
|---|---|---|
| `chat` | `chat.py` | 文字聊天 / 多模态理解（视觉走 chat 的 content 数组） |
| `token_count` | `token_count.py` | token 统计 / 预估 |
| `audio` | `audio.py` | 语音识别 (STT) / 语音合成 (TTS) |
| `image` | `image.py` | 文生图 / 图生图 |
| `video` | `video.py` | 视频生成 |
| `embedding` | `embedding.py` | 文本嵌入 (RAG) |
| `rerank` | `rerank.py` | 重排序 |

### 2.3 多模态视觉怎么走

**不需要单独的 image capability**。图片理解走的是 chat：

```json
{
  "model": "deepseek-v4-flash",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://..."}},
        {"type": "text", "text": "描述这张图"}
      ]
    }
  ]
}
```

chat.py 已经透传 `messages`，只要厂商支持 `image_url` content type 就能工作。

---

## 3. Step 0: 收集厂商信息

在写任何代码之前，先搞清楚：

| 信息 | 来源 | 示例 |
|---|---|---|
| base_url | API 文档 | `https://api.deepseek.com` |
| 认证方式 | API 文档 | Bearer token → header `Authorization: Bearer $KEY` |
| 模型列表 | `/models` 端点或文档 | deepseek-v4-flash, deepseek-v4-pro |
| 聊天端点 | API 文档 | `POST /chat/completions` |
| 流式格式 | API 文档 | SSE (标准 / 变种) |
| 支持参数 | API 文档 | tools? response_format? thinking? |
| 是否 OpenAI-compatible | 文档说明 | 是→chat.py 几乎不用改；否→需要改映射逻辑 |

---

## 3. Step 1: 生成样板文件

```python
from add_diy import scaffold

created = scaffold(
    "minimax",                      # 厂商名（目录用）
    base_url="https://api.minimax.com",
    vendor_model="abab-v6.5",       # 默认模型（只写一个对外的）
    api_key_env="MINIMAX_API_KEY",  # 不传则自动推导
    modules=["chat", "token_count", "audio", "image", "embedding"],
)
print(created)
# → {'model.json': Path(...), '__init__.py': Path(...),
#    'chat.py': Path(...), 'token_count.py': Path(...),
#    'audio.py': Path(...), 'image.py': Path(...), 'embedding.py': Path(...)}
```

`scaffold()` **不会覆盖已有文件**——已存在的文件保持不动。

各 capability 生成的模板类型：
- `chat` / `token_count` → **完整样板**（含参考实现，可直接改）
- `audio` / `image` / `video` / `embedding` / `rerank` → **最小骨架**（只有类名 + 工厂函数，agent 自己填业务逻辑）

---

## 4. Step 2: 修改 model.json

生成后，打开 `provider/<厂商>/model.json`：

```json
{
  "provider": "minimax",
  "enabled": true,
  "base_url": "https://api.minimax.com",
  "api_key_env": "MINIMAX_API_KEY",
  "modules": {
    "chat": "chat",
    "token_count": "token_count",
    "audio": "audio",
    "image": "image",
    "embedding": "embedding"
  },
  "models": {
    "abab-v6.5": {
      "capability": "chat",
      "vendor_model": "abab-v6.5",
      "supports_stream": true,
      "supports_tools": true,
      "supports_json_output": true,
      "supports_thinking": false
    }
  }
}
```

**model.json 字段说明：**

| 字段 | 必填 | 说明 |
|---|---|---|
| `provider` | ✅ | 厂商名，与目录名一致 |
| `enabled` | ✅ | `true`/`false`，整个厂商的开关 |
| `base_url` | ✅ | API base URL |
| `api_key_env` | ✅ | 环境变量名，程序从这里读密钥 |
| `modules` | ✅ | 声明此厂商提供哪些 capability，key=capability, value=模块文件名 |
| `models` | ✅ | 此厂商支持的模型列表，key 为 vendor_model |
| `models.*.capability` | ✅ | 模型能力分类：`chat` / `embedding` / `rerank` / ... |
| `models.*.vendor_model` | ✅ | 传给 API 的 model 参数值 |
| `models.*.supports_stream` | | 是否支持流式 |
| `models.*.supports_tools` | | 是否支持 function calling |
| `models.*.supports_json_output` | | 是否支持 JSON mode |
| `models.*.supports_thinking` | | 是否支持 reasoning/thinking |

**capability 可取值：** `chat`, `token_count`, `audio`, `image`, `video`, `embedding`, `rerank`

---

## 5. Step 3: 修改 chat.py 适配器

### 5.1 合约——必须保留的公开接口

```python
class XxxChat:
    async def invoke(self, request: dict) -> dict:
        """非流式。request/response 格式均为 OpenAI-compatible。"""
        ...

    async def invoke_stream(self, request: dict) -> AsyncIterator[dict]:
        """流式。yield 的每个 chunk 为 OpenAI-compatible。"""
        ...
```

### 5.2 需要改的方法（按厂商 API 文档）

| 方法 | 职责 | 何时需要改 |
|---|---|---|
| `_build_request_body()` | OpenAI 请求 → 厂商请求体 | 厂商不是标准 OpenAI 格式时 |
| `_build_headers()` | 认证头、Content-Type | 认证方式不是 `Bearer $KEY` 时 |
| `_normalize_response()` | 厂商响应 → OpenAI 响应 | 厂商响应字段名不同时 |
| `_normalize_stream_chunk()` | SSE chunk → OpenAI chunk | 厂商 SSE 字段不同时 |
| `_parse_sse()` | SSE 字节流 → JSON chunk | 厂商 SSE 不是标准 `data: {...}` 格式时 |

### 5.3 参数映射参考

OpenAI 标准参数 → 厂商参数对照，把不支持的参数剔除：

```
temperature     → temperature
top_p           → top_p
max_tokens      → max_tokens  (有些厂商叫 max_output_tokens)
stop            → stop
tools           → tools       (function calling)
tool_choice     → tool_choice
response_format → response_format  (json_object)
stream_options  → stream_options
```

### 5.4 响应归一化参考

统一响应格式（最小字段）：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "abab-v6.5",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "回复内容"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

流式 chunk 格式：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion.chunk",
  "created": 1234567890,
  "model": "abab-v6.5",
  "choices": [
    {
      "index": 0,
      "delta": {
        "role": "assistant",
        "content": "逐字"
      },
      "finish_reason": null
    }
  ],
  "usage": null
}
```

**关键点：** 流式最后一个 chunk 必须带 `usage`，非流式响应必须带 `usage`。

---

## 6. Step 4: 修改 token_count.py

一般不需要改。只有两种情况要改：

1. **厂商 usage 字段名和 OpenAI 不一致** → 修改 `normalize_usage()` 的字段映射
2. **厂商有公开 tokenizer** → 修改 `_load_tokenizer()` 返回该编码

| 统一 usage 字段 | 常见别名 |
|---|---|
| `prompt_tokens` | `input_tokens`, `prompt_length` |
| `completion_tokens` | `output_tokens`, `completion_length` |
| `total_tokens` | `total`, `sum` |
| `completion_tokens_details.reasoning_tokens` | `thinking_tokens`, `reason_tokens` |

---

## 7. Step 5: 编写非 chat 能力适配器（audio / image / embedding / ...）

### 7.1 骨架结构

`scaffold()` 生成的骨架文件格式一致：

```python
"""
Minimax audio 适配器（骨架）。

agent 按厂商 API 文档填充具体逻辑。
注意：
  - 类名和工厂函数名不要改（registry 靠它们发现模块）
  - __init__(config) 接收 model.json 的完整内容
"""

class MinimaxAudio:
    """audio 适配器。"""

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        # TODO: 从 cfg 读取 base_url / api_key_env 等
        self._enabled = cfg.get("enabled", True)

    # TODO: agent 在此添加业务方法


def create_audio(config=None):
    """工厂函数 — registry 通过此函数创建实例。"""
    return MinimaxAudio(config=config)
```

### 7.2 agent 需要做什么

1. **读 `cfg`** — `cfg["base_url"]`、`cfg["api_key_env"]`、`os.environ[cfg["api_key_env"]]` 拿到密钥
2. **写业务方法** — 按厂商文档的端点实现具体方法，方法签名自行定义
3. **更新 `model.json`** — models 里添加该 capability 的模型记录，标注 `capability`

### 7.3 例子：最小 embedding 实现

```python
import os
import httpx

class MinimaxEmbedding:
    def __init__(self, config=None):
        cfg = config or {}
        self._base_url = cfg.get("base_url", "").rstrip("/")
        env_key = cfg.get("api_key_env", "MINIMAX_API_KEY")
        self._api_key = os.environ.get(env_key, "")

    async def embed(self, request: dict) -> dict:
        body = {
            "model": request.get("model", "embo-01"),
            "input": request.get("input", ""),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                f"{self._base_url}/embeddings", json=body, headers=headers
            )
            return resp.json()
```

### 7.4 类名与工厂命名约定

| 规则 | 示例 (provider=minimax, capability=audio) |
|---|---|
| 类名 | `{PascalProvider}{PascalCapability}` → `MinimaxAudio` |
| 工厂名 | `create_{capability}` → `create_audio` |
| 文件名 | `{capability}.py` → `audio.py` |
| model.json modules key | `"audio": "audio"` |

**不要改这些命名**——registry 靠它们自动发现模块。

---

## 8. Step 6: 修改 __init__.py

样板的 `__init__.py` 已根据 `modules` 参数自动生成所有导入和工厂函数，一般不需要手改。

**core 加载规则（registry.py）：**
1. 先从 `provider/<name>/__init__.py` 找 `create_{module}(config)` 工厂
2. 找不到时回退到 `provider/<name>/{module}.py` 找同名工厂
3. 再找不到时用类名匹配：`{ProviderPascal}{CapabilityPascal}`

**类名推导规则：** `厂商名` 的 PascalCase + capability 后缀。如 `minimax` + `audio` → `MinimaxAudio`。

---

## 9. Step 7: 更新全局配置

### 9.1 config/config.json — 启用 provider

```json
{
  "providers": {
    "minimax": { "enabled": true }
  }
}
```

注意：此处的 key 必须与 provider 目录名完全一致。

### 9.2 config/models.json — 暴露模型给用户

新厂商的每个模型添加一条：

```json
{
  "minimax-abab-v6.5": {
    "provider": "minimax",
    "model": "abab-v6.5",
    "capability": "chat",
    "enabled": true,
    "visible": true
  },
  "minimax-embo-01": {
    "provider": "minimax",
    "model": "embo-01",
    "capability": "embedding",
    "enabled": true,
    "visible": true
  },
  "minimax-speech-01": {
    "provider": "minimax",
    "model": "speech-01",
    "capability": "audio",
    "enabled": true,
    "visible": true
  }
}
```

命名规则：`{provider}-{vendor_model}`，用 `-` 连接。这是外部用户看到的模型名。

### 9.3 config/api_keys.json — 给密钥添加模型权限

在现有密钥的 `models` 数组中添加新模型名：

```json
{
  "keys": {
    "sk-kemo-admin": {
      "models": [
        "minimax-abab-v6.5"
      ]
    }
  }
}
```

---

## 10. Step 8: 测试

### 10.1 命令行快测

```bash
cd E:\code\llm-adapter-kemo
export MINIMAX_API_KEY="your-key-here"

python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
from add_diy import ConnectivityTest

async def main():
    t = ConnectivityTest('provider/minimax')
    ok, err, resp = await t.test_chat('$MINIMAX_API_KEY', 'abab-v6.5')
    if ok:
        print('✅ 连通成功:', resp)
    else:
        print('❌', err)
    await t.close()

asyncio.run(main())
"
```

### 10.2 Core 集成测试

```bash
python3 -c "
import sys, json
sys.path.insert(0, '.')
from core import bootstrap

ctx = bootstrap('.')
print('providers:', ctx.registry.list_providers())
print('has_chat (minimax):', ctx.registry.has_capability('minimax', 'chat'))
print('models:', ctx.registry.list_models('minimax'))

route = ctx.router.resolve('minimax-abab-v6.5')
print('route:', route)
"
```

---

## 11. 契约检查清单

接入新厂商完成后逐项确认：

- [ ] `model.json` — base_url、api_key_env、models 字段完整，modules 包含全部 capability
- [ ] `__init__.py` — 所有 capability 类 + factory 函数均已导出
- [ ] `chat.py` — `invoke()` 和 `invoke_stream()` 可正常调用
- [ ] `chat.py` — 响应格式归一化为 OpenAI-compatible
- [ ] `chat.py` — 流式末 chunk 带 usage
- [ ] `token_count.py` — usage 字段正确映射
- [ ] 各 capability 骨架文件 — 类名 + 工厂符合命名约定
- [ ] `config/config.json` — provider 已添加并启用
- [ ] `config/models.json` — 所有模型已注册（`{provider}-{vendor_model}` 命名，标注对应 capability）
- [ ] `config/api_keys.json` — 至少一个密钥有该模型权限
- [ ] `core.registry` — 能扫描到并加载该 provider 的所有已声明模块
- [ ] `core.router` — 能解析暴露模型名到正确的 provider+model+capability
- [ ] `core.auth` — 密钥鉴权正常（包括白名单拒绝）

---

## 12. 常见问题

### Q: 厂商不是 OpenAI-compatible，怎么办？
先把 chat.py 里的 `_build_request_body()` 和 `_normalize_response()` 按厂商文档改好。`invoke()` 和 `invoke_stream()` 的签名不要动。

### Q: 厂商有语音/图像/嵌入模型，怎么加？
1. `scaffold()` 时在 `modules` 参数里加上对应 capability 名
2. 在 `model.json` 的 models 里添加模型记录，`capability` 标对
3. 打开骨架 `.py` 文件，按厂商文档写业务方法

### Q: 多模态视觉理解怎么处理？
不需要单独 capability。视觉理解走 chat，`content` 用数组格式 `[{type: "image_url", ...}, {type: "text", ...}]`。chat.py 已透传 messages。

### Q: 厂商只支持非流式/只支持流式？
只实现支持的。不支持的抛 `NotImplementedError`。

### Q: 厂商不支持 tools/function calling？
`model.json` 里 `supports_tools: false`，chat.py 的 `_build_request_body()` 不映射 tools 参数即可。

### Q: 厂商有多个模型，能力不同？
`model.json` 的 `models` 对象里每个模型一条，各自标注 `capability` 和 `supports_*`。

### Q: 骨架文件的类名可以自己取吗？
**不可以。** registry 靠 `{PascalProvider}{PascalCapability}` 命名来发现模块。自己取名会导致 registry 加载失败。

### Q: 直接复制 deepseek 目录改不行吗？
不行。deepseek 的 chat.py 有特有的 thinking 参数处理，会引入不该有的参数。从 `add_diy.scaffold()` 的干净样板开始。

### Q: 为什么不做自动探测？
每个厂商的 API 格式都不一样，自动探测做不通用。交给 agent 按各厂商文档手动确认更可靠。
