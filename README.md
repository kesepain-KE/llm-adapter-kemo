# Kemo LLM Adapter

> 多厂商 LLM 统一适配层 — 一套 API 接入多种大模型

Kemo LLM Adapter 是一个轻量级 API 网关，将多个厂商的 LLM 服务（DeepSeek、StepFun、MiniMax 等）统一暴露为 **OpenAI 兼容接口**。你只需挂载一个地址、一个密钥，就能切换和使用不同模型。

---

## 目录

- [背景](#背景)
- [特性](#特性)
- [项目架构](#项目架构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API 端点](#api-端点)
- [开发新厂商](#开发新厂商)
- [常见问题](#常见问题)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

---

## 背景

大模型厂商百花齐放，每种模型都有独立的 API 格式、鉴权方式和参数约定。同时接入多个厂商时，客户端需要维护大量适配逻辑，切换模型成本高。

Kemo LLM Adapter 将所有厂商的 API 统一为 **OpenAI 兼容格式**，客户端只需对接一个端点，通过修改模型名即可切换后端厂商。

## 特性

- **统一 API** — 全厂商统一 `/v1/chat/completions` 端点
- **流式支持** — SSE 流式响应，末 chunk 自动附带 usage
- **插件化厂商** — 每个厂商独立目录，`core/registry` 自动发现加载
- **密钥管理** — 每密钥独立模型白名单 + Token 配额控制
- **用量统计** — JSONL 日志，支持按密钥/厂商/模型汇总
- **配置热加载** — config.json、models.json、api_keys.json 修改无需重启
- **Web 管理面板** — 浏览器可视化管理厂商、模型、密钥
- **厂商脚手架** — `add_diy.scaffold()` 一键生成适配器样板
- **Docker 部署** — 开箱即用的 Docker Compose 配置
- **AI Agent 友好** — `agent_control.md` 指导 AI 自主完成厂商配置

## 项目架构

```
kemo-llm-adapter/
├── config/                  # 全局配置（热加载）
│   ├── config.json          # Provider 启停开关
│   ├── models.json          # 暴露模型名 → provider+model 映射
│   ├── api_keys.json        # 客户端密钥 + 白名单 + 配额
│   └── global_prompt.md     # 全局安全提示词
│
├── provider/<厂商名>/       # 每个厂商独立目录
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
├── web/                     # Web 管理面板前端
│
├── server.py                # 启动入口
├── setup.py                 # 初始化向导（推荐新用户使用）
├── agent_control.md         # AI Agent 操作手册
├── docker-compose.yml       # Docker 部署
└── Dockerfile               # 镜像构建
```

### 核心约定

| 约定 | 说明 |
|------|------|
| 模型命名 | `{provider}-{vendor_model}`，如 `deepseek-deepseek-v4-flash` |
| Provider 隔离 | 各厂商目录完全隔离，不互相 import |
| 请求/响应格式 | 统一为 OpenAI-compatible |
| 密钥来源 | Provider 从环境变量读取厂商 API 密钥 |

## 快速开始

### 前置条件

- Python >= 3.10
- pip

### 安装与启动

```bash
# 1. 克隆项目
git clone https://github.com/kesepain-KE/llm-adapter-kemo.git
cd llm-adapter-kemo

# 2. 一键初始化（环境检查 + 安装依赖 + 目录初始化 + 核心验证）
python setup.py

# 3. 编辑 provider.env，填入厂商 API 密钥
# 4. 编辑 config/api_keys.json，设置内部密钥

# 5. 启动服务
python server.py
```

服务默认运行在 `http://127.0.0.1:8741`。

> `setup.py` 是推荐的新手入口，它会逐一完成环境检查、依赖安装、目录创建和核心模块自检。也可用 `python setup.py --check` 仅检查环境。

### Docker 部署

```bash
docker-compose up -d
```

### 验证服务

```bash
# 健康检查
curl http://127.0.0.1:8741/health

# 查看可用模型
curl -H "Authorization: Bearer sk-your-key" http://127.0.0.1:8741/v1/models

# 聊天测试
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "deepseek-deepseek-v4-flash", "messages": [{"role": "user", "content": "你好"}]}'
```

## 配置说明

| 文件 | 作用 | 热加载 |
|------|------|--------|
| `config/config.json` | Provider 启停开关 | ✅ |
| `config/models.json` | 暴露模型名 → 厂商模型映射 | ✅ |
| `config/api_keys.json` | 客户端密钥 + 白名单 + 配额 | ✅ |
| `config/global_prompt.md` | 全局 system prompt | ✅ |
| `provider/*/model.json` | 厂商元信息 | ❌ 需重启 |
| `provider.env` | 厂商 API 密钥 | ❌ 需重启 |

详细配置示例请参考仓库中的 `provider.env.example` 及 `config/` 目录下的示例文件。

## API 端点

| 方法 | 路径 | 说明 | 需密钥 |
|------|------|------|--------|
| `GET` | `/` | Web 管理面板 | 否 |
| `GET` | `/health` | 健康检查 | 否 |
| `GET` | `/v1/models` | 列出可见模型 | 是 |
| `POST` | `/v1/chat/completions` | 聊天补全（流式 + 非流式） | 是 |
| `GET` | `/api/providers` | 厂商状态列表 | 是 |
| `POST` | `/api/providers/{name}/toggle` | 启用/禁用厂商 | 是 |
| `GET` | `/api/models` | 模型列表（含不可见） | 是 |
| `POST` | `/api/models/{id}/toggle` | 启用/禁用模型 | 是 |
| `POST` | `/api/models/{id}/test` | 模型连通性测试 | 是 |
| `GET` | `/api/keys` | 密钥列表 | 是 |
| `POST` | `/api/keys/{id}/models` | 修改密钥模型白名单 | 是 |
| `GET` | `/api/logs` | 调用日志 | 是 |
| `GET` | `/api/usage` | 用量统计 | 是 |
| `GET` | `/api/config` | 查看配置 | 是 |
| `POST` | `/api/config/{file}` | 保存配置 | 是 |

### 聊天请求示例

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

## 开发新厂商

使用脚手架工具一键生成适配器样板：

```python
from add_diy.scaffold import scaffold

created = scaffold(
    "minimax",
    base_url="https://api.minimax.com",
    vendor_model="abab-v6.5",
    modules=["chat", "token_count", "audio", "image"],
)
```

生成后还需：

1. 编辑 `provider/minimax/chat.py`，实现参数映射和响应归一化
2. 在 `config/models.json`、`api_keys.json`、`provider.env` 中注册
3. 重启服务

详细开发指南请参阅 `agent_control.md`。

## 常见问题

### 启动后 401

请求缺少 `Authorization: Bearer` 头，或密钥不在 `api_keys.json` 中。

### 配置修改后未生效

- `config/` 下的 JSON 文件 → 热加载，无需重启
- `provider/*/model.json`、`provider.env` → 需要重启

### 临时关闭某模型？

在 `models.json` 中将该模型 `enabled` 设为 `false`，无需重启。

### 如何接入新厂商？

使用 `add_diy.scaffold()` 生成样板，参考 `agent_control.md` 完成配置。

## 参与贡献

欢迎提交 PR 或 Issue。本项目的 AI Agent 操作手册 `agent_control.md` 可引导 AI 自主完成厂商适配开发与配置管理。

## 许可证

[MIT](LICENSE) © 2025 Kemo LLM Adapter Contributors
