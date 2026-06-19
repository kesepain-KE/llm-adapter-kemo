# Kemo LLM Adapter — 密钥创建指南

本文档面向 AI Agent，定义 API 密钥的完整创建流程。

---

## 目录

- [Step 0 — 了解密钥结构](#step-0--了解密钥结构)
- [Step 1 — 列出已有密钥并询问用户](#step-1--列出已有密钥并询问用户)
- [Step 2 — 生成密钥](#step-2--生成密钥)
- [Step 3 — 写入配置](#step-3--写入配置)
- [Step 4 — 验证密钥](#step-4--验证密钥)
- [Step 5 — 告知用户创建成功](#step-5--告知用户创建成功)
- [附录 A — 密钥管理速查](#附录-a--密钥管理速查)

---

## Step 0 — 了解密钥结构

### 密钥文件位置

```text
config/api_keys.json   ← 密钥存储
provider.env           ← 厂商 API 密钥（非本密钥）
```

### 密钥结构

```json
{
  "keys": {
    "sk-xxx": {
      "name": "密钥名称",
      "enabled": true,
      "models": ["模型名1", "模型名2"],
      "quota": {
        "total_tokens": 总配额,
        "used_tokens": 0
      }
    }
  }
}
```

### 各字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `sk-xxx`（密钥 ID） | ✅ | 客户端 `Authorization: Bearer sk-xxx` 用的值 |
| `name` | ✅ | 密钥名称，仅用于标识 |
| `enabled` | ✅ | `true` 启用 / `false` 禁用 |
| `models` | ✅ | 允许调用的模型名列表（对应 `config/models.json` 的 key） |
| `quota.total_tokens` | ✅ | 总配额 token 数（设为 0 表示不限） |
| `quota.used_tokens` | | 已使用 token（运行时自动更新，初始 0） |

### 密钥命名规范

密钥 ID 分两种情况：

| 类型 | 格式 | 示例 |
|------|------|------|
| **自动生成**（推荐） | `sk-{用途}-{40位随机十六进制}` | `sk-kemo-admin-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0` |
| **手动简短命名**（向后兼容） | `sk-{用途}` | `sk-kemo-admin` |

**自动生成的密钥 ID：**
- 前缀 `sk-`（表示 secret key）
- 中间 `{用途}`（如 `kemo-admin`, `kemo-guest`, `bot-xxx`）
- 后缀 `secrets.token_hex(20)` 生成 40 位十六进制（160 位安全强度）
- 总长度约 50~60 字符

**手动简短命名的密钥：**
- 用于已存在的旧密钥（如 `sk-kemo-admin`）
- 新密钥按自动生成规则创建，不手动写随机串

---

## Step 1 — 列出已有密钥并询问用户

### 1.1 先读取当前密钥列表

```python
import json
with open("config/api_keys.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for kid, info in data.get("keys", {}).items():
    print(f"  {kid[:20]}... → {info['name']} ({len(info['models'])} models, quota={info['quota']['total_tokens']:,})")
```

### 1.2 询问用户

```
当前已有密钥：
1. sk-kemo-admin-a1b2c3... → 管理员密钥 (9 models, quota=1,000,000,000)
2. sk-kemo-guest-c9d0e1... → 访客密钥 (2 models, quota=10,000,000)

请提供新密钥信息：
1. 密钥名称（如「我的个人密钥」「测试密钥」「开发密钥」）
2. 授权的模型（可选回复序号，如「全部」「1,3,5」）
3. Token 配额（如 1000000，或 0=不限）

可用模型列表：
1. deepseek-deepseek-v4-flash     — 快速聊天 ✅
2. deepseek-deepseek-v4-pro       — 深度推理 ✅
3. stepfun-step-3.7-flash         — 多模态聊天 ✅ vision
4. stepfun-stepaudio-2.5-tts      — 语音合成 ✅
5. stepfun-stepaudio-2.5-asr      — 语音识别 ✅
6. stepfun-step-image-edit-2      — 图生图 ✅
```

---

## Step 2 — 生成密钥

### 2.1 密钥 ID 生成规则

```python
import secrets

def generate_key_id(purpose: str = "kemo") -> str:
    """生成安全随机密钥 ID。

    格式: sk-{purpose}-{40位随机十六进制}
    总长度约 50~60 字符，安全强度 160 位。
    """
    random_part = secrets.token_hex(20)  # 40 hex chars = 160 bits
    return f"sk-{purpose}-{random_part}"
```

### 2.2 生成示例

```python
generate_key_id("kemo-admin")
# → sk-kemo-admin-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0

generate_key_id("kemo-guest")
# → sk-kemo-guest-c9d0e1f2a3b4c5d6e7f8a9b0a1b2c3d4e5f6a7b8

generate_key_id("bot-dev")
# → sk-bot-dev-e1f2a3b4c5d6e7f8a9b0a1b2c3d4e5f6a7b8c9d0
```

### 2.3 完整性校验

生成的密钥 ID 必须同时满足：
- 以 `sk-` 开头
- 总长度 ≥ 20 字符
- 包含至少 40 位随机十六进制字符

---

## Step 3 — 写入配置

### 3.1 读取当前 api_keys.json

```python
import json

with open("config/api_keys.json", "r", encoding="utf-8") as f:
    data = json.load(f)
```

### 3.2 添加新密钥

```python
import secrets

# 生成密钥 ID
random_part = secrets.token_hex(20)  # 40 hex chars
new_key_id = f"sk-kemo-guest-{random_part}"

new_key = {
    "name": "访客密钥",
    "enabled": True,
    "models": [
        "deepseek-deepseek-v4-flash",
        "stepfun-step-3.7-flash"
        # ← 用户选择的模型
    ],
    "quota": {
        "total_tokens": 10000000,  # ← 用户指定的配额
        "used_tokens": 0
    }
}

data["keys"][new_key_id] = new_key

with open("config/api_keys.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
```

### 3.3 完整配置示例

```json
{
  "keys": {
    "sk-kemo-admin-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0": {
      "name": "管理员密钥",
      "enabled": true,
      "models": [
        "deepseek-deepseek-v4-flash",
        "deepseek-deepseek-v4-pro",
        "stepfun-step-3.7-flash",
        "stepfun-stepaudio-2.5-tts",
        "stepfun-stepaudio-2.5-asr",
        "stepfun-step-image-edit-2"
      ],
      "quota": {
        "total_tokens": 1000000000,
        "used_tokens": 0
      }
    },
    "sk-kemo-guest-c9d0e1f2a3b4c5d6e7f8a9b0a1b2c3d4e5f6a7b8": {
      "name": "访客密钥",
      "enabled": true,
      "models": [
        "deepseek-deepseek-v4-flash",
        "stepfun-step-3.7-flash"
      ],
      "quota": {
        "total_tokens": 10000000,
        "used_tokens": 0
      }
    }
  }
}
```

---

## Step 4 — 验证密钥

### 4.1 验证方法

```bash
# 1. 查看模型列表（确认鉴权通过）
curl -H "Authorization: Bearer sk-xxx" http://127.0.0.1:8741/v1/models

# 2. 发起一次简单请求（确认配额和权限正常）
curl -X POST http://127.0.0.1:8741/v1/chat/completions ^
  -H "Authorization: Bearer sk-xxx" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"deepseek-deepseek-v4-flash\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":10}"

# 3. 验证无权限模型被拒绝（白名单生效）
curl -X POST http://127.0.0.1:8741/v1/chat/completions ^
  -H "Authorization: Bearer sk-xxx" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"stepfun-step-image-edit-2\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}"
# → 应返回 403
```

### 4.2 验证结果判断

| 结果 | 含义 | 操作 |
|------|------|------|
| `200` + 模型列表 | ✅ 鉴权通过 | 进入下一步 |
| `200` + 聊天响应 | ✅ 配额和权限正常 | 密钥可用 |
| `403 Model not allowed` | ✅ 白名单生效 | 安全策略正确 |
| `401` | ❌ 密钥未被识别 | 检查 api_keys.json 格式 |

---

## Step 5 — 告知用户创建成功

### 汇报模板

```
✅ 密钥创建成功

密钥 ID（已脱敏显示）：
  sk-kemo-xxx...xxxx

名称：访客密钥
授权模型：
  • deepseek-deepseek-v4-flash
  • stepfun-step-3.7-flash
Token 配额：10,000,000

⚠️ 请安全保存此密钥，退出对话后不再显示完整密钥。
配置已写入 config/api_keys.json，无需重启即可生效。
```

---

## 附录 A — 密钥管理速查

### 常见操作

| 场景 | 操作 |
|------|------|
| 加/删模型白名单 | 编辑 `api_keys.json` 中对应密钥的 `models` 数组 |
| 调整配额 | 修改 `quota.total_tokens` |
| 禁用密钥（暂时） | 设 `enabled: false` |
| 重新启用 | 设 `enabled: true` |
| 用量清零 | 将 `used_tokens` 重置为 `0` |
| 删除密钥 | 从 `keys` 对象移除整条记录 |

### 鉴权流程（用于排查）

```
客户端请求
  → 提取 Authorization: Bearer sk-xxx
  → auth.py 在 api_keys.json 中查找 sk-xxx
  → 检查 enabled / models 白名单 / quota
  → 通过 → 路由到对应 provider
  → 拒绝 → 返回 401/403
```

### 安全注意事项

- `config/api_keys.json` **已加入 `.gitignore`**，不会提交到 Git
- 新密钥**必须**使用 `secrets.token_hex()` 生成随机后缀（160 位安全强度）
- 现存的简短密钥（如 `sk-kemo-admin`）为历史遗留，新密钥不再采用此格式
- 生产环境建议定期轮换密钥
- 密钥写入配置后**无需重启服务**，即写即生效

### Python 快速生成命令

```bash
# 一行生成安全密钥（purpose 替换为实际用途）
python -c "import secrets; print(f'sk-kemo-{secrets.token_hex(20)}')"
```
