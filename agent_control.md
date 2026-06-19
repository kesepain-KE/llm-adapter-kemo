# Kemo LLM Adapter — Agent 操作手册

> **工作流索引 →** 详见 `add_diy/` 目录下的各流程文件。

---

## 新厂商接入工作流

按照以下顺序执行，**不要跳过**：

**① 读取厂商 API 文档、用户提供的 key 和 base_url**
→ 了解请求/响应格式、端点、鉴权方式、能力范围。

**② 最小化连通测试**
→ 用厂商原生端点（curl / Python）确认 key 和 base_url 有效。
→ 拉取厂商模型列表，询问用户需要接入哪些模型。

**③ 读取接入指南**
→ 打开 `add_diy/build_adapter.md`，按流程在本项目注册新厂商。

**④ 读取厂商文档，编写适配模块**
→ 按需实现 `chat.py`、`token_count.py`、`audio.py`、`image.py` 等。
→ 注册至 `provider/<厂商名>/` 目录，完成 `model.json` 和 `__init__.py`。

**⑤ 批量测试能力**
→ 对每个已注册模型分层测试（chat / vision / audio / image / embedding），在 models.json 中标上正确的能力标签。

**⑥ 完成收尾**
→ 告知用户注册成功，并提供新模型的暴露名、能力概览、调用方式。
→ **如需特殊说明**（如音色映射、厂商限制、尺寸规格、价格、参数差异等），在 `provider/<厂商名>/explain.md` 中记录，便于后续查阅。
→ **确保新厂商的模型完全适配本项目的模型注册与使用机制**：命名规则 `{provider}-{vendor_model}`、热加载、OpenAI 兼容响应格式、API Key 鉴权与白名单。若厂商接口与本项目规范有差异，通过适配层（adapter）抹平，不绕过统一框架。

> 本文件是**入口索引**，指引 AI Agent 找到具体的操作流程文件。
>
> 各流程的完整步骤在 `add_diy/` 目录下，**请勿跳过直接操作**。

---

## 快速导航

| 你要做什么 | 去读这个文件 |
|-----------|-------------|
| **接入新厂商**（从测试到注册全流程） | → `add_diy/build_adapter.md` |
| **创建 API 密钥**（随机生成 + 授权模型 + 配额） | → `add_diy/build_key.md` |

---

## 项目速览

```
llm-adapter-kemo/
├── add_diy/                 ← 🎯 操作指引 + 工具
│   ├── build_adapter.md     ← 新厂商接入（7 步完整流程）
│   ├── build_key.md         ← 密钥创建（5 步完整流程）
│   └── api_test.py          ← 连通测试工具（空壳，待实现）
│
├── config/                  ← 全局配置（热加载）
│   ├── config.json          ← provider 启停开关
│   ├── models.json          ← 暴露模型名 → provider+model 映射
│   ├── api_keys.json        ← 客户端密钥 + 白名单 + 配额
│   └── global_prompt.md     ← 全局安全提示词
│
├── provider/<厂商名>/       ← 每个厂商独立目录（隔离，不互相 import）
│   ├── model.json           ← 厂商元信息（base_url, api_key_env, 模型列表）
│   ├── __init__.py          ← 导出适配器类 + 工厂函数
│   ├── chat.py              ← 聊天适配器（invoke + invoke_stream）
│   ├── token_count.py       ← Token 统计（normalize_usage + estimate_tokens）
│   ├── audio.py             ← 音频适配器（按需）
│   ├── image.py             ← 图像适配器（按需）
│   ├── embedding.py         ← 嵌入适配器（按需）
│   └── ...
│
├── core/                    ← 编排层（一般不改）
│   ├── registry.py          ← 自动扫描 provider/*/model.json 加载模块
│   ├── router.py            ← 解析 models.json 暴露模型名
│   ├── auth.py              ← 密钥鉴权 + 模型白名单
│   ├── call_log.py          ← 请求日志 (JSON Lines)
│   └── usage.py             ← 用量统计 + 额度管理
│
├── api/                     ← FastAPI 服务层
│   ├── app.py               ← FastAPI 应用入口
│   ├── routes/              ← 路由
│   └── services/            ← 业务逻辑
│
├── provider.env             ← 厂商 API 密钥（不提交到 Git）
├── server.py                ← 启动入口
├── setup.py                 ← 初始化向导 / 环境检查
├── start.ps1                ← Windows 启动脚本
└── requirements.txt         ← Python 依赖
```

**核心约定：**
- 模型命名：`{provider}-{vendor_model}`（如 `deepseek-deepseek-v4-flash`）
- 响应格式：统一 OpenAI-compatible
- 密钥来源：厂商密钥从环境变量读，客户端密钥从 `api_keys.json` 读

**热加载规则：**
| 文件 | 需重启 |
|------|--------|
| `config/*.json` | ❌ 不用 |
| `provider/*/model.json` / `provider.env` / `provider/*.py` | ✅ **必须重启** |

---

## 常见操作入口

```bash
# 启动服务器
python server.py --port 8741

# 健康检查
curl http://127.0.0.1:8741/api/health

# 查看可用模型
curl -H "Authorization: Bearer sk-your-key" http://127.0.0.1:8741/v1/models
```

---

> 详细流程请始终以 `add_diy/build_adapter.md` 和 `add_diy/build_key.md` 为准。
> 本文件仅作索引，不包含操作细节。
