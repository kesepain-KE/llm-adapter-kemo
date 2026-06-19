# Kemo LLM Adapter

<p align="center">
  <img src="./llm-adapter-kemo.png" alt="Kemo LLM Adapter" width="300">
</p>

> 多厂商 LLM 统一适配层 — 一套 OpenAI 兼容 API 接入多种大模型  
> Multi-provider LLM unification layer — one OpenAI-compatible API to rule them all

---

## 目录 / Table of Contents

- [简介 / Introduction](#简介--introduction)
- [快速开始 / Quick Start](#快速开始--quick-start)
- [API 文档（AI Agent 专用） / API Docs for AI Agent](#api-文档ai-agent-专用--api-docs-for-ai-agent)
- [更多能力 / Additional Capabilities](#更多能力--additional-capabilities)
- [配置参考 / Configuration Reference](#配置参考--configuration-reference)
- [项目架构 / Project Architecture](#项目架构--project-architecture)
- [相关项目 / Related Projects](#相关项目--related-projects)
- [许可证 / License](#许可证--license)

---

## 简介 / Introduction

**中文**  
Kemo LLM Adapter 是一个轻量级 API 网关，将 DeepSeek、StepFun、MiniMax 等多家大模型厂商的服务统一暴露为 **OpenAI 兼容接口**。客户端只需挂载一个地址、一个 API Key，通过修改 `model` 参数即可切换后端厂商。

**English**  
Kemo LLM Adapter is a lightweight API gateway that unifies multiple LLM providers (DeepSeek, StepFun, MiniMax, etc.) behind a single **OpenAI-compatible API**. Your client connects to one endpoint with one API key, and switches providers by changing the `model` parameter.

### 特性 / Features

| 中文 | English |
|------|---------|
| 统一 API — 全厂商 `/v1/chat/completions` 端点 | Unified API — single `/v1/chat/completions` endpoint for all providers |
| 流式与非流式 | Streaming + non-streaming supported |
| 插件化厂商 — 每个厂商独立目录，自动发现加载 | Pluggable providers — each provider is a self-contained directory, auto-discovered |
| 密钥管理 — 每密钥独立模型白名单 + Token 配额 | Key management — per-key model whitelist + token quota |
| 用量统计 — JSONL 日志，按密钥/厂商/模型汇总 | Usage tracking — JSONL logging, aggregated by key/provider/model |
| 配置热加载 — 修改配置无需重启 | Hot-reload — config changes take effect without restart |
| React Web 管理面板 | React Web admin panel |
| 厂商脚手架 — 一键生成适配器样板 | Provider scaffold — one-click adapter boilerplate generation |
| AI Agent 友好 — 支持 AI 自主完成厂商配置 | AI Agent friendly — AI can self-configure new providers |

---

## 快速开始 / Quick Start

### 前置条件 / Prerequisites

- Python >= 3.10
- pip
- Node.js >= 20 & npm（仅 Web 面板需要 / only needed for admin panel）

### 获取项目 / Get the Project

```bash
git clone https://github.com/kesepain-KE/llm-adapter-kemo.git
cd llm-adapter-kemo
```

### 初始化 / Initialize

```bash
python setup.py
```

可用选项 / Available flags:
- `--check` — 仅检查环境 / check environment only
- `--install` — 仅安装依赖 / install dependencies only
- `--validate` — 仅核心自检 / validate core modules only

### 配置厂商密钥 / Configure Provider Keys

```bash
cp provider.env.example provider.env
cp config/api_keys.json.example config/api_keys.json
cp config/models.json.example config/models.json
```

编辑 `provider.env`，填入厂商 API 密钥 / Edit `provider.env` and fill in your provider API keys。

支持两种配置方式 / Two configuration options:
- **AI 自动配置 / AI-automated** — 让 AI 助手读取 `agent_control.md` 自动完成
- **手动编辑 / Manual** — 直接编辑 `provider.env` + `config/` 下各配置文件

### 构建 Web 面板 / Build Admin Panel

```bash
cd web && npm install && npm run build && cd ..
```

### 启动 / Start

```bash
python server.py
```

服务默认运行在 `http://127.0.0.1:8741`。

---

## API 文档（AI Agent 专用） / API Docs for AI Agent

所有端点均兼容 OpenAI 格式，AI Agent 可像调用 OpenAI API 一样使用。

> **注意**：`/api/*` 管理接口仅用于 Web 管理面板，AI Agent 无需关心。

### 基础地址 / Base URL

```
http://<your-host>:8741
```

### 鉴权 / Authentication

所有请求需在 Header 中携带 Bearer Token：

```bash
Authorization: Bearer sk-your-key
```

密钥由 `config/api_keys.json` 配置，支持独立模型白名单和配额控制。

### 模型列表 / List Models

```
GET /v1/models
```

返回所有可见的模型列表 / Returns all visible models：

```json
{
  "object": "list",
  "data": [
    {
      "id": "deepseek-deepseek-v4-flash",
      "object": "model",
      "created": 1700000000,
      "owned_by": "deepseek"
    }
  ]
}
```

### 聊天补全 / Chat Completions

```
POST /v1/chat/completions
```

完全兼容 OpenAI Chat Completions API，支持流式和非流式。  
Fully OpenAI-compatible. Supports both streaming and non-streaming.

**请求示例 / Example Request：**

```bash
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-deepseek-v4-flash",
    "messages": [
      {"role": "user", "content": "你好"}
    ],
    "temperature": 0.7,
    "max_tokens": 1024,
    "stream": false
  }'
```

**参数 / Parameters：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | string | — | 模型 ID（见 `/v1/models`） |
| `messages` | array | — | 消息数组（OpenAI 格式） |
| `temperature` | number | 1.0 | 采样温度 |
| `top_p` | number | 1.0 | Nucleus sampling |
| `max_tokens` | integer | 4096 | 最大生成 token 数 |
| `stream` | boolean | false | 是否流式返回 |
| `stop` | string/array | null | 停止序列 |

### 语音合成 / Text-to-Speech

```
POST /v1/audio/speech
```

生成语音音频 / Generate speech audio。

```bash
curl -X POST http://127.0.0.1:8741/v1/audio/speech \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "input": "你好，世界",
    "voice": "alloy"
  }'
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | TTS 模型 ID |
| `input` | string | 要合成的文本（最多 4096 字符） |
| `voice` | string | 语音风格：alloy / echo / fable / onyx / nova / shimmer |
| `response_format` | string | 输出格式：mp3 / opus / aac / flac / wav / pcm |

### 语音转文字 / Speech-to-Text

```
POST /v1/audio/transcriptions
```

将音频文件转录为文字 / Transcribe audio to text。

```bash
curl -X POST http://127.0.0.1:8741/v1/audio/transcriptions \
  -H "Authorization: Bearer sk-your-key" \
  -F "file=@audio.mp3" \
  -F "model=whisper-1"
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 转录模型 ID |
| `file` | file | 音频文件（mp3 / wav / ogg 等） |
| `language` | string | 语言代码（可选，如 `zh`） |

### 图像生成 / Image Generation

```
POST /v1/images/generations
```

根据文字描述生成图片 / Generate images from text descriptions。

```bash
curl -X POST http://127.0.0.1:8741/v1/images/generations \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dall-e-3",
    "prompt": "一只可爱的猫",
    "n": 1,
    "size": "1024x1024"
  }'
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 图像模型 ID |
| `prompt` | string | 图片描述 |
| `n` | integer | 生成数量（1-4） |
| `size` | string | 尺寸：1024x1024 / 1792x1024 / 1024x1792 |
| `quality` | string | 质量：standard / hd |

### 图像编辑 / Image Editing

```
POST /v1/images/edits
```

基于图片和蒙版进行编辑 / Edit images with a mask。

### 向量嵌入 / Embeddings

```
POST /v1/embeddings
```

获取文本的向量表示 / Get text embeddings。

```bash
curl -X POST http://127.0.0.1:8741/v1/embeddings \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text-embedding-3-small",
    "input": "需要嵌入的文本"
  }'
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 嵌入模型 ID |
| `input` | string/array | 要嵌入的文本 |

### 重排序 / Rerank

```
POST /v1/rerank
```

对检索结果进行重排序 / Re-rank search results。

### 视频生成 / Video Generation

```
POST /v1/videos/generations
GET /v1/videos/{job_id}
GET /v1/videos/{job_id}/content
```

异步视频生成，提交后通过 job_id 轮询状态。  
Async video generation — submit, then poll with job_id。

---

## 更多能力 / Additional Capabilities

### 厂商脚手架 / Provider Scaffold

用 Python 一键生成新厂商适配器样板 / Generate a new provider adapter with one command：

```python
from add_diy.scaffold import scaffold

created = scaffold(
    "minimax",
    base_url="https://api.minimax.com",
    vendor_model="abab-v6.5",
    modules=["chat", "token_count", "audio", "image"],
)
```

生成后 / After generation：
1. 编辑 `provider/minimax/chat.py` 实现参数映射和响应归一化
2. 在 `config/models.json`、`api_keys.json`、`provider.env` 中注册
3. 重启服务

详细开发指南见 `agent_control.md`。

### 管理面板 / Admin Panel

访问 `http://127.0.0.1:8741/` 进入 React Web 管理面板，可在其中管理厂商、模型、密钥、查看日志和用量统计。默认凭据由 `provider.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 配置。

### 配置热加载 / Hot Reload

| 文件 | 作用 | 热加载 |
|------|------|--------|
| `config/config.json` | Provider 启停开关 | ✅ |
| `config/models.json` | 暴露模型名 → 厂商模型映射 | ✅ |
| `config/api_keys.json` | 客户端密钥 + 白名单 + 配额 | ✅ |
| `config/global_prompt.md` | 全局 system prompt | ✅ |
| `provider/*/model.json` | 厂商元信息 | ❌ 需重启 |
| `provider.env` | 厂商 API 密钥 | ❌ 需重启 |

---

## 配置参考 / Configuration Reference

| 文件 / File | 用途 / Purpose | 热加载 |
|-------------|----------------|--------|
| `provider.env` | 厂商 API 密钥（从环境变量读取） | ❌ |
| `config/config.json` | Provider 启停开关 | ✅ |
| `config/models.json` | 暴露模型名 → 厂商模型映射 | ✅ |
| `config/api_keys.json` | 客户端密钥 + 白名单 + 配额 | ✅ |
| `config/global_prompt.md` | 全局 system prompt | ✅ |
| `provider/*/model.json` | 厂商元信息（base_url, api_key_env 等） | ❌ |

配置示例文件位于各文件的 `.example` 副本中。

模型命名约定 / Model naming convention：

```
{provider}-{vendor_model}
```

示例 / Example：`deepseek-deepseek-v4-flash`

---

## 项目架构 / Project Architecture

```
llm-adapter-kemo/
├── config/                  # 全局配置（热加载）
│   ├── config.json          # Provider 启停开关
│   ├── models.json          # 暴露模型名 → provider+model 映射
│   ├── api_keys.json        # 客户端密钥 + 白名单 + 配额
│   └── global_prompt.md     # 全局安全提示词
│
├── provider/<name>/         # 每个厂商独立目录
│   ├── model.json           # 厂商元信息（base_url, api_key_env 等）
│   ├── chat.py              # 聊天适配器（invoke + invoke_stream）
│   ├── token_count.py       # Token 统计归一化
│   ├── audio.py             # 音频适配器（可选）
│   └── image.py             # 图像适配器（可选）
│
├── core/                    # 编排层
│   ├── registry.py          # 自动扫描加载 provider 模块
│   ├── router.py            # 解析模型名 → provider + model
│   ├── auth.py              # Bearer 鉴权 + 模型白名单
│   ├── call_log.py          # 统一调用日志（JSONL）
│   └── usage.py             # Token 用量统计 + 配额扣减
│
├── api/                     # FastAPI 服务层
├── add_diy/                 # 脚手架工具包
├── web/                     # React/Vite Web 管理面板
│   ├── src/                 # React 源码
│   ├── package.json         # 前端依赖与构建脚本
│   └── dist/                # 构建产物（本地生成，不提交）
│
├── server.py                # 启动入口
├── setup.py                 # 初始化向导
└── agent_control.md         # AI Agent 操作手册
```

### 核心约定 / Core Conventions

| 约定 / Convention | 说明 / Description |
|-------------------|--------------------|
| 模型命名 | `{provider}-{vendor_model}`，如 `deepseek-deepseek-v4-flash` |
| Provider 隔离 | 各厂商目录完全隔离，不互相 import |
| 请求/响应格式 | 统一为 OpenAI-compatible |
| 密钥来源 | Provider 从环境变量读取厂商 API 密钥 |

---

## 相关项目 / Related Projects

- [VOTX Agent](https://github.com/kesepain-KE/votx-agent) — 多用户 AI Agent 框架，本项目的 AI Agent 操作手册即面向此类系统  
  Multi-user AI Agent framework — this project's AI agent control docs target such systems

---

## 许可证 / License

[MIT](LICENSE) © 2025 Kemo LLM Adapter Contributors
