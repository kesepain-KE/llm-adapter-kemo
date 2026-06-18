# Kemo LLM Adapter — Agent 操作手册

本文档面向 AI Agent，覆盖项目的完整操作流程：配置管理、密钥管理、服务部署、新厂商接入、故障排查。

---

## 目录

- [1. 项目架构速览](#1-项目架构速览)
- [2. 配置清单 — 三份核心文件](#2-配置清单--三份核心文件)
- [3. API 密钥管理](#3-api-密钥管理)
- [4. 服务器部署与运维](#4-服务器部署与运维)
- [5. Provider 接入流程](#5-provider-接入流程)
- [6. Capability 开发指南](#6-capability-开发指南)
- [7. 测试与验证](#7-测试与验证)
- [8. API 端点参考](#8-api-端点参考)
- [9. 常见问题与排查](#9-常见问题与排查)
- [10. 契约检查清单](#10-契约检查清单)

---

## 1. 项目架构速览

```
kemo-llm-adapter/
├── config/                  ← 全局配置（用户每天要改的）
│   ├── config.json          ← provider 启停开关
│   ├── models.json          ← 暴露给用户的模型名 → provider+model 映射
│   ├── api_keys.json        ← API 密钥 + 模型白名单 + 配额
│   └── global_prompt.md     ← 全局安全提示词（纯文本）
│
├── provider/<厂商名>/       ← 每个厂商独立目录
│   ├── model.json           ← 厂商元信息（base_url, api_key_env, 模型列表, 能力）
│   ├── __init__.py          ← 导出所有 capability 类 + create_* 工厂
│   ├── chat.py              ← 聊天适配器
│   ├── token_count.py       ← Token 统计
│   ├── audio.py             ← 音频适配器（骨架）
│   ├── image.py             ← 图像适配器（骨架）
│   ├── embedding.py         ← 嵌入适配器（骨架）
│   └── ...                  ← 其他 capability 按需添加
│
├── core/                    ← 编排层（一般不改）
│   ├── registry.py          ← 自动扫描 provider/*/model.json 加载模块
│   ├── router.py            ← 解析 models.json 暴露模型名
│   ├── auth.py              ← 密钥鉴权 + 模型白名单
│   ├── call_log.py          ← 请求日志 (JSON Lines)
│   └── usage.py             ← 用量统计 + 持久化
│
├── api/                     ← FastAPI 服务层
│   ├── app.py               ← FastAPI 应用入口
│   ├── routes/              ← 路由（v1.py 为主）
│   └── services/            ← 业务逻辑
│
├── add_diy/                 ← 工具包
│   ├── scaffold.py          ← 生成 provider/<name>/ 样板文件
│   └── test.py              ← 最小连通测试
│
├── provider.env             ← 厂商 API 密钥（已 gitignore）
├── server.py                ← 启动入口
├── setup.py                 ← 初始化向导
├── start.ps1                ← Windows 启动脚本
├── start.sh                 ← Linux 启动脚本
├── docker-compose.yml       ← Docker 部署
├── Dockerfile               ← 镜像构建
└── requirements.txt         ← Python 依赖
```

### 核心约定

| 规则 | 说明 |
|------|------|
| 命名格式 | `{provider}-{vendor_model}`，如 `deepseek-deepseek-v4-flash` |
| provider 隔离 | 各 provider 目录完全隔离，不互相 import |
| 统一格式 | 请求/响应均为 OpenAI-compatible |
| 密钥来源 | provider 从环境变量读厂商 API 密钥，不从配置文件读 |

---

## 2. 配置清单 — 三份核心文件

### 2.1 `config/config.json` — Provider 开关

控制哪些厂商启用。key 必须与 `provider/<目录名>` 一致。

```json
{
  "providers": {
    "deepseek": { "enabled": true },
    "stepfun":  { "enabled": true },
    "minimax":  { "enabled": false }
  }
}
```

| 字段 | 说明 |
|------|------|
| `providers.<name>.enabled` | `true` 启用 / `false` 禁用该厂商所有模型 |

### 2.2 `config/models.json` — 模型注册表

定义暴露给最终用户的模型名 → provider + model + capability 映射。

```json
{
  "deepseek-deepseek-v4-flash": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "capability": "chat",
    "enabled": true,
    "visible": true,
    "extra": {}
  }
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| key | ✅ | 对外模型名，格式 `{provider}-{vendor_model}` |
| `provider` | ✅ | 对应 `provider/<目录名>` |
| `model` | ✅ | 传给厂商 API 的 model 参数值 |
| `capability` | ✅ | `chat` / `audio` / `image` / `embedding` / `rerank` / `video` |
| `enabled` | ✅ | `true` / `false`，可临时关闭 |
| `visible` | ✅ | `true` 用户可见 / `false` 隐藏（仍可用） |
| `extra` | | 附加参数，如 `thinking` 配置 |

**capability 可取值：**

| 值 | 说明 |
|----|------|
| `chat` | 文字聊天 + 多模态视觉理解 |
| `audio` | 语音识别 (STT) + 语音合成 (TTS) |
| `image` | 文生图 / 图生图 |
| `embedding` | 文本嵌入向量 |
| `rerank` | 重排序 |
| `video` | 视频生成 |

### 2.3 `config/api_keys.json` — 内部密钥定义

定义调用此 API 的客户端密钥。每个密钥有独立的模型白名单和配额。

```json
{
  "keys": {
    "sk-your-admin-key": {
      "name": "管理员密钥",
      "enabled": true,
      "models": [
        "deepseek-deepseek-v4-flash",
        "deepseek-deepseek-v4-pro"
      ],
      "quota": {
        "total_tokens": 1000000000,
        "used_tokens": 0
      }
    }
  }
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| key | ✅ | 密钥 ID（客户端用此值作为 `Authorization: Bearer sk-xxx`） |
| `name` | ✅ | 密钥名称，仅用于标识 |
| `enabled` | ✅ | `true` 启用 / `false` 禁用 |
| `models` | ✅ | 允许此密钥调用的模型名列表（对应 models.json 的 key） |
| `quota.total_tokens` | ✅ | 总配额 token 数 |
| `quota.used_tokens` | | 已使用 token（运行时自动更新） |

### 2.4 `config/global_prompt.md` — 全局安全提示词

纯文本文件，内容会在每次 chat 请求时自动注入到 system message 中。
可用于添加安全过滤、输出格式要求等。空文件或不存在则跳过。

### 2.5 `provider/<name>/model.json` — 厂商元信息

每个 provider 目录下必有的元信息文件（详见 [5.2 修改 model.json](#52-修改-modeljson)）。

---

## 3. API 密钥管理

### 3.1 创建新密钥

在 `config/api_keys.json` 的 `keys` 对象中添加一条：

```json
{
  "keys": {
    "sk-alice-key": {
      "name": "Alice 的个人密钥",
      "enabled": true,
      "models": ["deepseek-deepseek-v4-flash"],
      "quota": {
        "total_tokens": 50000000,
        "used_tokens": 0
      }
    }
  }
}
```

**密钥 ID 命名建议：** `sk-<用途>`，如 `sk-admin`、`sk-guest`、`sk-bot-xxx`。

### 3.2 修改密钥

场景及操作：

| 场景 | 操作 |
|------|------|
| 加/删模型白名单 | 编辑 `models` 数组 |
| 调整配额 | 修改 `quota.total_tokens` |
| 禁用密钥 | 设 `enabled: false`（保留记录，暂不开放） |
| 启用密钥 | 设 `enabled: true` |
| 用量清零 | 将 `used_tokens` 重置为 `0` |

### 3.3 删除密钥

从 `keys` 对象中移除整条记录即可。注意：已删除的密钥发来的请求会被直接拒绝。

### 3.4 查看用量

用量数据存储在 `data_status/call_log/` 目录下，按密钥 ID 分文件：

```
data_status/call_log/
  sk-kemo-admin.jsonl       ← 管理员密钥的调用日志
  sk-kemo-guest.jsonl       ← 访客密钥的调用日志
```

每条日志格式：

```json
{
  "timestamp": "2026-06-18T12:00:00Z",
  "model": "deepseek-deepseek-v4-flash",
  "prompt_tokens": 150,
  "completion_tokens": 300,
  "total_tokens": 450,
  "cost": 0.0025,
  "status": "success"
}
```

可用 API 端点 `/admin/usage` 查看汇总用量（详见[第8章](#8-api-端点参考)）。

### 3.5 密钥鉴权流程

```
客户端请求
  → 提取 Authorization: Bearer sk-xxx
  → auth.py 在 api_keys.json 中查找 sk-xxx
  → 检查 enabled / models 白名单 / 配额
  → 通过 → 路由到对应 provider
  → 拒绝 → 返回 401/403
```

### 3.6 安全注意事项

- 密钥 ID 不要太简单（避免被猜到）
- `api_keys.json` **已加入 `.gitignore`**，不会提交到 Git
- 首次部署需从 `api_keys.json.example` 复制并修改
- 生产环境建议通过环境变量或密钥管理服务注入

---

## 4. 服务器部署与运维

### 4.1 启动方式

#### 方式一：直接启动（开发环境）

```bash
# 确保 provider.env 已配置真实密钥
python server.py

# 指定端口和主机
python server.py --port 8741 --host 0.0.0.0

# 热重载模式（开发用）
python server.py --reload
```

#### 方式二：使用启动脚本

```bash
# Windows（自动加载 provider.env）
.\start.ps1

# Linux / macOS（自动加载 provider.env）
./start.sh
```

启动脚本的功能：
1. 读取 `provider.env` 设置环境变量
2. 创建 `data_status/call_log/` 目录（如不存在）
3. 启动 `server.py`

#### 方式三：uvicorn 直接启动

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8741
```

#### 方式四：Docker 部署

```bash
# 确保 provider.env 已配置好
docker-compose up -d

# 查看日志
docker-compose logs -f
```

Docker 会自动挂载：
- `./data_status` → 日志持久化
- `./config` → 配置目录（只读，方便热改）

### 4.2 验证服务是否正常

```bash
# 健康检查
curl http://127.0.0.1:8741/health
# → {"status": "ok", "providers": 2, "models": 5}

# 查看可用模型（需一个有效密钥）
curl -H "Authorization: Bearer sk-your-key" http://127.0.0.1:8741/v1/models

# 快速聊天测试
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "deepseek-deepseek-v4-flash", "messages": [{"role": "user", "content": "你好"}]}'
```

### 4.3 日志与监控

| 来源 | 位置/方式 | 说明 |
|------|-----------|------|
| 请求日志 | `data_status/call_log/<key-id>.jsonl` | 每次 API 调用的明细 |
| 服务日志 | stdout（控制台/`docker logs`） | 服务运行日志 |
| 健康检查 | `GET /health` | 快速检查服务状态 |

### 4.4 配置热改

`config/` 目录下的三个核心配置文件（`config.json`、`models.json`、`api_keys.json`）
**修改后无需重启**，下次请求会自动读取最新内容。

`provider.env` 和 `provider/<name>/model.json` 的修改**需要重启**服务器。

### 4.5 首次部署快速流程

```bash
# 1. 从示例模板创建配置
cp provider.env.example provider.env
cp config/api_keys.json.example config/api_keys.json
cp config/models.json.example config/models.json

# 2. 编辑 provider.env，填入你的厂商 API 密钥
# 3. 编辑 api_keys.json，设置你的内部密钥
# 4. 编辑 models.json，注册你的模型

# 5. 安装依赖
pip install -r requirements.txt

# 6. 启动
python server.py
```

---

## 5. Provider 接入流程

当用户要求「接入 XXX 厂商」时，按以下步骤操作。**不要跳步。**

### 5.0 收集厂商信息

在写任何代码之前，先查清这些信息：

| 信息 | 来源 | 示例 |
|------|------|------|
| `base_url` | API 文档 | `https://api.deepseek.com` |
| 认证方式 | API 文档 | Bearer token / API Key Header |
| 模型列表 | `/models` 端点或文档 | `deepseek-v4-flash` |
| 聊天端点 | API 文档 | `POST /chat/completions` |
| 流式格式 | API 文档 | SSE（标准 / 变种）|
| 支持参数 | API 文档 | tools? response_format? thinking? |
| 是否 OpenAI-compatible | 自行判断 | 是→chat.py 几乎不改；否→需映射 |

### 5.1 生成样板文件

```python
from add_diy import scaffold

created = scaffold(
    "minimax",                      # 厂商名（目录名）
    base_url="https://api.minimax.com",
    vendor_model="abab-v6.5",       # 默认模型
    api_key_env="MINIMAX_API_KEY",  # 不传则自动推导
    modules=["chat", "token_count", "audio", "image", "embedding"],
)
# → 生成 provider/minimax/ 下的所有样板文件
```

**`scaffold()` 不会覆盖已有文件。** 各能力生成的模板类型：

| capability | 模板类型 |
|------------|----------|
| `chat` / `token_count` | **完整样板**（含参考实现，可直接改） |
| `audio` / `image` / `video` / `embedding` / `rerank` | **最小骨架**（类名+工厂，需填业务逻辑） |

### 5.2 修改 model.json

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
| `enabled` | ✅ | `true`/`false`，整个厂商开关 |
| `base_url` | ✅ | API base URL |
| `api_key_env` | ✅ | 环境变量名（程序从 `os.environ` 读密钥） |
| `modules` | ✅ | capability → 文件名映射 |
| `models` | ✅ | 此厂商支持的模型列表 |
| `models.*.capability` | ✅ | `chat` / `audio` / `image` / `embedding` / ... |
| `models.*.vendor_model` | ✅ | 传给厂商 API 的 model 参数 |
| `models.*.supports_stream` | | 是否支持流式 |
| `models.*.supports_tools` | | 是否支持 function calling |
| `models.*.supports_json_output` | | 是否支持 JSON mode |
| `models.*.supports_thinking` | | 是否支持 thinking/reasoning |
| `models.*.supports_reasoning` | | 是否支持 `reasoning_effort` 参数 |

### 5.3 修改 chat.py 适配器

**必须保留的公开接口：**

```python
class MinimaxChat:
    async def invoke(self, request: dict) -> dict:
        """非流式。request/response 格式均为 OpenAI-compatible。"""
        ...

    async def invoke_stream(self, request: dict) -> AsyncIterator[dict]:
        """流式。yield 的每个 chunk 为 OpenAI-compatible。"""
        ...
```

**按需修改的方法：**

| 方法 | 职责 | 何时改 |
|------|------|--------|
| `_build_request_body()` | OpenAI 请求 → 厂商请求体 | 厂商不是标准 OpenAI 格式时 |
| `_build_headers()` | 认证头 | 认证方式不是 Bearer 时 |
| `_normalize_response()` | 厂商响应 → OpenAI 响应 | 字段名不同时 |
| `_normalize_stream_chunk()` | SSE chunk → OpenAI chunk | SSE 字段不同时 |
| `_parse_sse()` | SSE 字节流 → JSON chunk | SSE 不是标准格式时 |

**参数映射参考：**

```
OpenAI 标准             厂商（按需映射）
temperature      →     temperature
top_p            →     top_p
max_tokens       →     max_tokens / max_output_tokens
stop             →     stop / stop_sequences
tools            →     tools
tool_choice      →     tool_choice
response_format  →     response_format (json_object)
stream_options   →     stream_options
user             →     user / user_id

非标准扩展参数：
reasoning_effort →     reasoning_effort (low/medium/high)
thinking         →     thinking ({"type": "enabled"})
reasoning_format →     reasoning_format
```

**响应归一化（非流式）：**

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "abab-v6.5",
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
  "model": "abab-v6.5",
  "choices": [{
    "index": 0,
    "delta": {"role": "assistant", "content": "逐字"},
    "finish_reason": null
  }],
  "usage": null
}
```

**关键：** 流式最后一个 chunk 必须带 `usage`，非流式必须带 `usage`。

### 5.4 修改 token_count.py

一般不需要改。两种情况需要改：

1. **厂商 usage 字段名不一致** → 修改 `normalize_usage()` 的字段映射
2. **厂商有公开 tokenizer** → 修改 `_load_tokenizer()` 返回该编码

| 统一字段 | 常见别名 |
|----------|----------|
| `prompt_tokens` | `input_tokens`, `prompt_length` |
| `completion_tokens` | `output_tokens`, `completion_length` |
| `total_tokens` | `total`, `sum` |
| `completion_tokens_details.reasoning_tokens` | `thinking_tokens`, `reason_tokens` |

### 5.5 更新 __init__.py

`scaffold()` 已自动生成，一般不需要手改。

**core 加载规则的优先级：**
1. `provider/<name>/__init__.py` → `create_{module}(config)` 工厂
2. `provider/<name>/{module}.py` → `create_{module}(config)` 工厂
3. 类名匹配：`{PascalProvider}{PascalCapability}`

**类名推导：** `minimax` + `audio` → `MinimaxAudio`

### 5.6 更新全局配置

**Step A — 启用 provider：**

在 `config/config.json` 中添加：

```json
{
  "providers": {
    "minimax": { "enabled": true }
  }
}
```

key 必须与 `provider/<目录名>` 一致。

**Step B — 注册模型到 models.json：**

```json
{
  "minimax-abab-v6.5": {
    "provider": "minimax",
    "model": "abab-v6.5",
    "capability": "chat",
    "enabled": true,
    "visible": true
  }
}
```

命名规则：`{provider}-{vendor_model}`，用 `-` 连接。

**Step C — 给密钥添加模型权限：**

```json
{
  "keys": {
    "sk-your-key": {
      "models": ["minimax-abab-v6.5"]
    }
  }
}
```

**Step D — 在 provider.env 添加密钥：**

```bash
# 追加到 provider.env
MINIMAX_API_KEY=your-real-api-key
MINIMAX_BASE_URL=https://api.minimax.com
```

环境变量名必须与 `model.json` 的 `api_key_env` 一致。

**Step E — 重启服务器**

修改 `model.json` 或 `provider.env` 后需要重启：

```bash
# 如果正在运行，Ctrl+C 后重新启动
python server.py
```

---

## 6. Capability 开发指南

### 6.1 骨架结构

`scaffold()` 生成的骨架文件格式一致：

```python
"""Minimax audio 适配器（骨架）。"""

class MinimaxAudio:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._enabled = cfg.get("enabled", True)

def create_audio(config=None):
    return MinimaxAudio(config=config)
```

### 6.2 类名与工厂命名约定

| 规则 | 示例（provider=minimax, capability=audio） |
|------|---------------------------------------------|
| 类名 | `{PascalProvider}{PascalCapability}` → `MinimaxAudio` |
| 工厂名 | `create_{capability}` → `create_audio` |
| 文件名 | `{capability}.py` → `audio.py` |
| model.json modules key | `"audio": "audio"` |

**不要改这些命名** — registry 靠它们自动发现模块。

### 6.3 完整示例：embedding 实现

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

### 6.4 多模态视觉理解

**不需要单独的 image capability。** 视觉理解走 chat，content 用数组格式：

```json
{
  "model": "deepseek-deepseek-v4-flash",
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

chat.py 已透传 `messages`，只要厂商支持 `image_url` content type 就能工作。

### 6.5 Registry 发现规则

`core/registry.py` 自动发现并加载模块：

1. 读 `provider/<name>/model.json` 的 `modules` 字段
2. 对每个 capability key，查找对应模块文件
3. 先调 `__init__.py` 的工厂 → 再调 `{module}.py` 的工厂 → 最后用类名匹配
4. 匹配到后注入 `model.json` 配置并实例化

**这意味着**：只要在 `model.json` 的 `modules` 里声明 capability，并在目录下创建对应文件（含类+工厂），registry 无需任何修改就能加载。

---

## 7. 测试与验证

### 7.1 连通性测试（单厂商）

```bash
set MINIMAX_API_KEY=your-key-here

python -c "
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

### 7.2 Core 集成测试（全系统）

```bash
python -c "
import sys
sys.path.insert(0, '.')
from core import bootstrap

ctx = bootstrap('.')
print('providers:', ctx.registry.list_providers())
print('has chat (minimax):', ctx.registry.has_capability('minimax', 'chat'))
print('models:', ctx.registry.list_models('minimax'))
route = ctx.router.resolve('minimax-abab-v6.5')
print('route:', route)
"
```

### 7.3 HTTP 测试（全链路）

```bash
# 1. 健康检查
curl http://127.0.0.1:8741/health

# 2. 查看可用模型
curl -H "Authorization: Bearer sk-your-key" http://127.0.0.1:8741/v1/models

# 3. 非流式聊天
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "minimax-abab-v6.5", "messages": [{"role": "user", "content": "1+1=?"}]}'

# 4. 流式聊天
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "minimax-abab-v6.5", "messages": [{"role": "user", "content": "数到5"}], "stream": true}'
```

---

## 8. API 端点参考

| 方法 | 路径 | 说明 | 需要密钥 |
|------|------|------|----------|
| `GET` | `/health` | 健康检查 | 否 |
| `GET` | `/v1/models` | 列出所有可见模型 | 是 |
| `POST` | `/v1/chat/completions` | 聊天补全（非流式+流式） | 是 |
| `GET` | `/admin/keys` | 列出所有密钥（管理面板） | 是 |
| `GET` | `/admin/usage` | 用量汇总 | 是 |
| `GET` | `/admin/stats` | 统计数据 | 是 |
| `GET` | `/admin/providers` | 厂商状态 | 是 |
| `GET` | `/admin/logs` | 调用日志 | 是 |

### 请求示例

```bash
# 标准 OpenAI-compatible 聊天请求
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-deepseek-v4-flash",
    "messages": [{"role": "user", "content": "你好"}],
    "temperature": 0.7,
    "max_tokens": 1024,
    "stream": false
  }'
```

---

## 9. 常见问题与排查

### Q: 启动后 "401 Unauthorized"

**原因：** 请求中没有 `Authorization` 头，或密钥不在 `api_keys.json` 中。

**排查：**
```bash
# 检查密钥文件
cat config/api_keys.json | head -20

# 确认密钥 ID 存在
curl -H "Authorization: Bearer sk-your-key" http://127.0.0.1:8741/v1/models
```

### Q: 启动后 "403 Forbidden"

**原因：** 密钥存在但被禁用（`enabled: false`），或请求的模型不在密钥白名单中。

**排查：** 检查 `api_keys.json` 中该密钥的 `enabled` 和 `models` 字段。

### Q: 模型调用返回 "Model not found"

**原因：** 请求的模型名不在 `models.json` 中，或 `enabled: false`。

**排查：**
```bash
# 查看已注册的模型
curl -H "Authorization: Bearer sk-your-key" http://127.0.0.1:8741/v1/models
```

### Q: 请求报 "502 Provider error"

**原因：** 厂商 API 密钥无效、余额不足、或网络不通。

**排查：**
```bash
# 检查 provider.env 中的密钥是否正确
# 用 curl 直调厂商 API 验证
curl -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  https://api.deepseek.com/v1/models
```

### Q: 启动后提示找不到模块（ImportError）

**原因：** 缺少依赖或 provider 目录结构不完整。

**排查：**
```bash
pip install -r requirements.txt
python setup.py --check
python setup.py --validate
```

### Q: 修改配置后未生效

| 修改对象 | 是否需要重启 |
|----------|-------------|
| `config/config.json` | ❌ 不重启（热加载） |
| `config/models.json` | ❌ 不重启（热加载） |
| `config/api_keys.json` | ❌ 不重启（热加载） |
| `provider/<name>/model.json` | ✅ **需要重启** |
| `provider.env` | ✅ **需要重启** |
| `provider/<name>/*.py` | ✅ **需要重启** |

### Q: `setup.py` 向导怎么用？

```bash
# 完整向导（推荐首次使用）
python setup.py

# 仅检查环境
python setup.py --check

# 仅安装依赖
python setup.py --install

# 仅核心自检
python setup.py --validate
```

### Q: 如何临时关闭某个模型或厂商？

```bash
# 关闭单个模型 → models.json 中设 "enabled": false
# 关闭整个厂商 → config.json 中设 "enabled": false
# 两者都不需要重启
```

### Q: 直接复制 deepseek 目录改不行吗？

**不行。** deepseek 的 chat.py 有特有的 thinking 参数处理，会引入不该有的参数。
始终从 `add_diy.scaffold()` 的干净样板开始。

### Q: 厂商只支持非流式 / 只支持流式？

只实现支持的。不支持的抛 `NotImplementedError`。

### Q: 厂商不支持 tools / function calling？

`model.json` 里设 `supports_tools: false`，chat.py 的 `_build_request_body()` 不映射 tools 参数即可。

### Q: 厂商有多个模型，能力不同？

`model.json` 的 `models` 对象里每个模型一条，各自标注 `capability` 和 `supports_*`。

---

## 10. 契约检查清单

接入新厂商完成后逐项确认：

### Provider 目录

- [ ] `model.json` — base_url、api_key_env、models 字段完整，modules 包含全部 capability
- [ ] `__init__.py` — 所有 capability 类 + factory 函数均已导出
- [ ] `chat.py` — `invoke()` 和 `invoke_stream()` 签名正确
- [ ] `chat.py` — 响应格式归一化为 OpenAI-compatible
- [ ] `chat.py` — 流式末 chunk 带 usage
- [ ] `token_count.py` — usage 字段正确映射
- [ ] 各 capability 骨架文件 — 类名 + 工厂符合命名约定

### 全局配置

- [ ] `config/config.json` — provider 已添加并启用
- [ ] `config/models.json` — 所有模型已注册（`{provider}-{vendor_model}` 命名）
- [ ] `config/api_keys.json` — 至少一个密钥有该模型权限
- [ ] `provider.env` — 已添加对应 `api_key_env` 的环境变量

### Core 验证

- [ ] `core.registry` — 能扫描到并加载该 provider 的所有已声明模块
- [ ] `core.router` — 能解析暴露模型名到正确的 provider+model+capability
- [ ] `core.auth` — 密钥鉴权正常（白名单放行/拒绝）

### 功能测试

- [ ] `add_diy.test()` — 连通性测试通过
- [ ] HTTP 非流式调用正常
- [ ] HTTP 流式调用正常
- [ ] 不存在的模型返回正确错误
- [ ] 无效密钥返回 401/403
- [ ] 请求日志写入 `data_status/call_log/`
