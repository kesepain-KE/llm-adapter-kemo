# Kemo LLM Adapter

<p align="center">
  <img src="./llm-adapter-kemo.png" alt="Kemo LLM Adapter" width="300">
</p>

> 多厂商 LLM 统一适配层 — 一套 API 接入多种大模型

Kemo LLM Adapter 是一个轻量级 API 网关，将多个厂商的 LLM 服务（DeepSeek、StepFun、MiniMax 等）统一暴露为 **OpenAI 兼容接口**。你只需挂载一个地址、一个密钥，就能切换和使用不同模型。

---

## 目录

- [背景](#背景)
- [安装](#安装)
- [用法](#用法)
- [项目架构](#项目架构)
- [相关项目](#相关项目)
- [主要项目负责人](#主要项目负责人)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

---

## 背景

大模型厂商百花齐放，每种模型都有独立的 API 格式、鉴权方式和参数约定。同时接入多个厂商时，客户端需要维护大量适配逻辑，切换模型成本高。

Kemo LLM Adapter 将所有厂商的 API 统一为 **OpenAI 兼容格式**，客户端只需对接一个端点，通过修改模型名即可切换后端厂商。

### 特性

- 统一 API — 全厂商统一 `/v1/chat/completions` 端点，流式与非流式皆可
- 插件化厂商 — 每个厂商独立目录，`core/registry` 自动发现加载，新增厂商无需改框架代码
- 密钥管理 — 每密钥独立模型白名单 + Token 配额控制
- 用量统计 — JSONL 日志，支持按密钥、厂商、模型汇总
- 配置热加载 — config.json、models.json、api_keys.json 修改无需重启
- React Web 管理面板 — Vite + React 可视化管理厂商、模型、密钥
- 厂商脚手架 — `add_diy.scaffold()` 一键生成适配器样板
- AI Agent 友好 — `agent_control.md` 指导 AI 自主完成厂商配置

## 安装

### 前置条件

- Python >= 3.10
- pip
- Node.js >= 20 与 npm（本地构建/开发 Web 管理面板需要）

### 获取项目

```bash
git clone https://github.com/kesepain-KE/llm-adapter-kemo.git
cd llm-adapter-kemo
```

### 初始化

```bash
python setup.py
```

setup.py 是初始化向导，依次完成 Python 版本检查、依赖检测（缺依赖时询问是否安装）、创建必要目录 `data_status/call_log/` 和 `provider/`、核心模块自检。另可用 `python setup.py --check` 仅检查环境，`--install` 仅安装依赖，`--validate` 仅核心自检。

### 配置

```bash
# 复制示例配置
cp provider.env.example provider.env
cp config/api_keys.json.example config/api_keys.json
cp config/models.json.example config/models.json
```

配置厂商密钥有两种方式：

**方式 A — 让 AI Agent 代劳（推荐）**
让你的 AI 助手阅读 `agent_control.md`，自动完成厂商接入与密钥配置。

**方式 B — 手动编辑**
- `provider.env` — 填入各厂商 API 密钥
- `config/api_keys.json` — 设置内部密钥及配额
- `config/models.json` — 注册要暴露的模型

### 构建 Web 管理面板

```bash
cd web
npm install
npm run build
cd ..
```

构建产物写入 `web/dist/`，FastAPI 会在访问 `/` 时返回该 React 页面。

### 启动

```bash
python server.py
```

服务默认运行在 `http://127.0.0.1:8741`。

前端开发时可以同时运行 Vite，Vite 会把 `/api` 与 `/v1` 代理到本地后端：

```bash
python server.py
cd web && npm run dev
```

## 用法

### 配置说明

| 文件 | 作用 | 热加载 |
|------|------|--------|
| `config/config.json` | Provider 启停开关 | ✅ |
| `config/models.json` | 暴露模型名 → 厂商模型映射 | ✅ |
| `config/api_keys.json` | 客户端密钥 + 白名单 + 配额 | ✅ |
| `config/global_prompt.md` | 全局 system prompt | ✅ |
| `provider/*/model.json` | 厂商元信息 | ❌ 需重启 |
| `provider.env` | 厂商 API 密钥 | ❌ 需重启 |

详细配置示例见 `provider.env.example` 及 `config/` 目录下的 `.example` 文件。

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | Web 管理面板 |
| `GET` | `/health` | 健康检查 |
| `GET` | `/v1/models` | 列出可见模型 |
| `POST` | `/v1/chat/completions` | 聊天补全（流式 + 非流式） |
| `GET` | `/api/providers` | 厂商状态列表 |
| `POST` | `/api/providers/{name}/toggle` | 启用/禁用厂商 |
| `GET` | `/api/models` | 模型列表（含不可见） |
| `POST` | `/api/models/{id}/toggle` | 启用/禁用模型 |
| `POST` | `/api/models/{id}/test` | 模型连通性测试 |
| `GET` | `/api/keys` | 密钥列表 |
| `POST` | `/api/keys/{id}/models` | 修改密钥模型白名单 |
| `GET` | `/api/logs` | 调用日志 |
| `GET` | `/api/usage` | 用量统计 |
| `GET` | `/api/config` | 查看配置 |
| `POST` | `/api/config/{file}` | 保存配置 |

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

### 开发新厂商

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

详细开发指南见 `agent_control.md`。

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
├── web/                     # React/Vite Web 管理面板
│   ├── src/                 # React 源码
│   ├── package.json         # 前端依赖与构建脚本
│   └── dist/                # 构建产物（本地生成，不提交）
│
├── server.py                # 启动入口
├── setup.py                 # 初始化向导
└── agent_control.md         # AI Agent 操作手册
```

### 核心约定

| 约定 | 说明 |
|------|------|
| 模型命名 | `{provider}-{vendor_model}`，如 `deepseek-deepseek-v4-flash` |
| Provider 隔离 | 各厂商目录完全隔离，不互相 import |
| 请求/响应格式 | 统一为 OpenAI-compatible |
| 密钥来源 | Provider 从环境变量读取厂商 API 密钥 |

## 相关项目

- [VOTX Agent](https://github.com/kesepain-KE/votx-agent) — 多用户 AI Agent 框架，本项目的 AI Agent 操作手册即面向此类系统

## 主要项目负责人

- [@kesepain-KE](https://github.com/kesepain-KE)

## 参与贡献

欢迎提交 PR 或 Issue。`agent_control.md` 可引导 AI 自主完成厂商适配开发与配置管理，降低人工贡献门槛。

### 贡献人员

感谢所有为项目做出贡献的人。

## 许可证

[MIT](LICENSE) © 2025 Kemo LLM Adapter Contributors
