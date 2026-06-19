# Kemo LLM Adapter — Agent 操作手册

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
kemo-llm-adapter/
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
