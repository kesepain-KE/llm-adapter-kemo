<p align="center">
  <img src="https://img.shields.io/badge/English-%F0%9F%87%AC%F0%9F%87%A7%20README_EN.md-blue?style=for-the-badge&logo=markdown" alt="English" />
</p>

<p align="center">
  <a href="./README_EN.md"><strong>📖 Read the English Guide →</strong></a>
  <br>
  <sub>Quick setup, API reference, configuration &amp; provider development in English</sub>
</p>

---
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
- [API 文档 / API Reference](#api-文档--api-reference)
- [供应商适配 / Provider Development](#供应商适配--provider-development)
- [配置参考 / Configuration Reference](#配置参考--configuration-reference)
- [项目架构 / Project Architecture](#项目架构--project-architecture)
- [相关项目 / Related Projects](#相关项目--related-projects)
- [许可证 / License](#许可证--license)

---

## 简介 / Introduction

**中文**  
Kemo LLM Adapter 是一个轻量级 API 网关，将 DeepSeek、StepFun 等多家大模型厂商的服务统一暴露为 **OpenAI 兼容接口**。客户端只需挂载一个地址、一个 API Key，通过修改 `model` 参数即可切换后端厂商。

**English**  
Kemo LLM Adapter is a lightweight API gateway that unifies multiple LLM providers (DeepSeek, StepFun, etc.) behind a single **OpenAI-compatible API**. Your client connects to one endpoint with one API key, and switches providers by changing the `model` parameter.

### 特性 / Features

| 中文 | English |
|------|---------|
| 统一 API — 全厂商统一的 OpenAI 兼容端点 | Unified API — OpenAI-compatible interface across all providers |
| 流式与非流式 — 流式完成后记录 usage 并扣减配额 | Streaming + non-streaming, with usage accounting after streams finish |
| 多模态扩展 — TTS / ASR / 图像 / 视频 | Multi-modal extensions — TTS, ASR, image, video |
| 插件化厂商 — 每个厂商独立目录，自动发现加载 | Pluggable providers — self-contained directories, auto-discovered |
| 密钥管理 — 每密钥独立模型白名单 + Token 配额 | Key management — per-key model whitelist + token quota |
| 用量统计 — JSONL 日志，按密钥/厂商/模型/能力汇总 | Usage tracking — JSONL logging, aggregated by key/provider/model/capability |
| 配置热加载 — 修改配置无需重启 | Hot-reload — config changes take effect without restart |
| React Web 管理面板 | React Web admin panel |
| 厂商接入指南 — Agent 可按流程创建适配器 | Provider onboarding guide — agents can create adapters by following the workflow |
| AI Agent 友好 — 支持 AI 自主完成厂商配置 | AI Agent friendly — AI can self-configure new providers |
| Git 更新 — 自动备份保护用户配置 | Git-based updates — automated with user config protection |

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

`python setup.py` 会在文件缺失时自动生成空的运行态配置：

- `provider.env` 从 `provider.env.example` 复制
- `config/config.json` 从 `config/config.json.example` 复制
- `config/models.json` 默认 `{}`
- `config/api_keys.json` 默认 `{"keys": {}}`

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

### 更新 / Update

```bash
python update.py            # 交互式更新
python update.py --check    # 仅检查版本
python update.py --yes      # 非交互式更新
```

更新脚本会自动备份 `config/` 和 `provider.env`，拉取代码后恢复，确保用户配置不丢失。

---

## API 文档 / API Reference

所有端点均兼容 OpenAI 格式。  
All endpoints are OpenAI-compatible.

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

### 管理端点 / Admin Endpoints

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 服务健康检查 |
| `GET` | `/api/providers` | 厂商列表与状态 |
| `POST` | `/api/providers/{name}/toggle` | 启用/禁用厂商 |
| `GET` | `/api/models` | 模型列表（含不可见） |
| `POST` | `/api/models/{id}/toggle` | 启用/禁用模型 |
| `POST` | `/api/models/{id}/test` | 模型连通性测试（可用性 + 响应延迟） |
| `GET` | `/api/keys` | 密钥列表 |
| `POST` | `/api/keys/{id}/models` | 更新密钥白名单 |
| `GET` | `/api/logs` | 调用日志 |
| `GET` | `/api/stats` | 仪表盘统计 |
| `GET` | `/api/usage` | 用量汇总 |
| `GET` | `/api/config` | 全局 Prompt 查看 |
| `POST` | `/api/config/global_prompt` | 保存全局 Prompt |

### 模型列表 / List Models

```
GET /v1/models
```

```json
{
  "object": "list",
  "data": [
    { "id": "deepseek-deepseek-v4-flash", "object": "model", "owned_by": "deepseek" },
    { "id": "deepseek-deepseek-v4-pro",   "object": "model", "owned_by": "deepseek" },
    { "id": "stepfun-step-3.7-flash",     "object": "model", "owned_by": "stepfun" }
  ]
}
```

### 聊天补全 / Chat Completions

```
POST /v1/chat/completions
```

完全兼容 OpenAI Chat Completions API，支持流式和非流式。流式请求会尽量强制上游返回 `usage`，服务层在流结束后写入调用日志并扣减配额。

```bash
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

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `model` | string | — | 模型 ID（见 `/v1/models`） |
| `messages` | array | — | OpenAI 格式消息数组 |
| `temperature` | number | 1.0 | 采样温度 |
| `top_p` | number | 1.0 | Nucleus sampling |
| `max_tokens` | integer | 4096 | 最大生成 token 数 |
| `stream` | boolean | false | 是否流式 |
| `stop` | string/array | null | 停止序列 |
| `tools` | array | null | 工具/函数调用定义 |
| `response_format` | object | null | 如 `{"type": "json_object"}` |

### 语音合成 / Text-to-Speech

```
POST /v1/audio/speech
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 模型 ID（如 `stepfun-stepaudio-2.5-tts`） |
| `input` | string | 要合成的文本（最多 1000 字符） |
| `voice` | string | 音色 ID（详见 `provider/*/explain.md`） |
| `response_format` | string | mp3 / wav / flac / opus / pcm |
| `speed` | number | 语速 0.5～2.0 |

### 语音转文字 / Speech-to-Text

```
POST /v1/audio/transcriptions
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 模型 ID（如 `stepfun-stepaudio-2.5-asr`） |
| `file` | file | 音频文件（mp3 / wav / ogg 等） |
| `language` | string | 语言代码（可选） |

### 图像生成 / Image Generation

```
POST /v1/images/generations
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 模型 ID |
| `prompt` | string | 图片描述 |
| `n` | integer | 生成数量 |
| `size` | string | 如 `1024x1024` |
| `response_format` | string | url / b64_json |

### 图像编辑 / Image Editing

```
POST /v1/images/edits
```

Multipart/form-data，包含 `image` 文件 + `prompt` + `model`。

### 向量嵌入 / Embeddings / 重排序 / Rerank / 视频生成 / Video Generation

```
POST /v1/embeddings
POST /v1/rerank
POST /v1/videos/generations
GET  /v1/videos/{job_id}
GET  /v1/videos/{job_id}/content
```

后端实际可用模型取决于已注册的厂商及 models.json 配置。

---

## 供应商适配 / Provider Development

### 内置厂商 / Built-in Providers

| 厂商 | 模块 | 能力 |
|------|------|------|
| **DeepSeek** | `provider/deepseek/` | chat · token_count |
| **StepFun** | `provider/stepfun/` | chat · token_count · audio (TTS/ASR) · image |

### 厂商接入指南 / Provider Onboarding

`add_diy/` 当前提供 Agent 操作流程文档，不提供可导入的 Python 自动生成器。接入新厂商时先阅读 `agent_control.md`，再按 `add_diy/build_adapter.md` 手动创建 `provider/<name>/` 目录和适配文件。

创建后：
1. 编辑 `provider/minimax/chat.py` 实现参数映射和响应归一化
2. 编辑 `provider/minimax/token_count.py`，确保真实 usage、流式 usage、缓存 token、推理 token 都能归一化
3. 在 `config/models.json` 中注册暴露名
4. 在 `provider.env` 中配置 API Key
5. 重启服务

详细开发指南见 `agent_control.md`。

### 模型命名约定 / Model Naming Convention

```
{provider}-{vendor_model}
```

示例：`deepseek-deepseek-v4-flash` → provider=`deepseek`, vendor_model=`deepseek-v4-flash`

### 管理面板 / Admin Panel

访问 `http://127.0.0.1:8741/` 进入 React Web 管理面板，可在其中管理厂商、模型、密钥、查看日志和用量统计。默认凭据由 `provider.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 配置。

---

## 配置参考 / Configuration Reference

| 文件 | 用途 | 热加载 |
|------|------|--------|
| `provider.env` | 厂商 API 密钥（从环境变量读取） | ❌ 需重启 |
| `config/config.json` | Provider 启停开关 | ✅ |
| `config/models.json` | 暴露模型名 → 厂商模型映射 | ✅ |
| `config/api_keys.json` | 客户端密钥 + 白名单 + 配额 | ✅ |
| `config/global_prompt.md` | 全局 system prompt | ✅ |
| `provider/*/model.json` | 厂商元信息（base_url, api_key_env 等） | ❌ 需重启 |

配置示例文件位于各文件的 `.example` 副本中。

统计日期按应用时区切分，默认 `Asia/Shanghai`；如需改为其他时区，可在环境变量或 `provider.env` 中设置 `KEMO_TIMEZONE`。

### model.json 注册格式

```json
{
  "deepseek-deepseek-v4-flash": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "capabilities": ["chat"],
    "endpoint": "/v1/chat/completions",
    "enabled": true,
    "visible": true
  },
  "stepfun-stepaudio-2.5-tts": {
    "provider": "stepfun",
    "model": "stepaudio-2.5-tts",
    "capabilities": ["audio.tts"],
    "endpoint": "/v1/audio/speech",
    "enabled": true,
    "visible": true
  }
}
```

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
│   ├── __init__.py          # bootstrap() + AppContext（DI 容器）
│   ├── registry.py          # 自动扫描加载 provider 模块
│   ├── router.py            # 模型名 → provider + model 解析
│   ├── auth.py              # Bearer 鉴权 + 模型白名单
│   ├── call_log.py          # 统一调用日志（JSONL）
│   └── usage.py             # Token 用量 + 额度扣减
│
├── api/                     # FastAPI 服务层
│   ├── app.py               # 应用入口
│   ├── routes/              # 路由处理器
│   ├── services/            # 服务逻辑（鉴权、日志、统计）
│   └── utils/               # 工具函数
│
├── add_diy/                 # 厂商接入与密钥创建流程文档
├── web/                     # React/Vite Web 管理面板
│   ├── src/                 # React 源码
│   ├── package.json         # 前端依赖与构建脚本
│   └── dist/                # 构建产物（本地生成）
│
├── server.py                # 服务启动入口
├── setup.py                 # 初始化向导
├── update.py                # Git 更新脚本（自动备份用户配置）
├── requirements.txt         # Python 依赖清单
├── version.json             # 版本号
└── agent_control.md         # AI Agent 操作手册
```

### 核心约定 / Core Conventions

| 约定 | 说明 |
|------|------|
| 模型命名 | `{provider}-{vendor_model}`，如 `deepseek-deepseek-v4-flash` |
| Provider 隔离 | 各厂商目录完全隔离，不互相 import |
| 请求/响应格式 | 统一为 OpenAI-compatible |
| 密钥来源 | Provider 从环境变量读取厂商 API 密钥 |
| 工厂优先加载 | 模块通过 `create_*` 工厂函数创建，回退到类直接初始化 |
| 配置保护 | `update.py` 自动备份 `config/`、`provider.env`，更新后恢复 |

---

## 相关项目 / Related Projects

- [VOTX Agent](https://github.com/kesepain-KE/votx-agent) — 多用户 AI Agent 框架，本项目的 AI Agent 操作手册即面向此类系统  
  Multi-user AI Agent framework — this project's AI agent control docs target such systems

---

## 许可证 / License

[MIT](LICENSE) © 2025 Kemo LLM Adapter Contributors
