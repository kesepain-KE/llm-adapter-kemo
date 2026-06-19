# Kemo LLM Adapter — API 示例文档

服务地址示例: `http://127.0.0.1:8741`。

> 默认提交的仓库不包含任何 provider 实现、真实模型或真实密钥。本文件中的 `your-provider-*`、`sk-your-client-key` 等内容均为占位示例。新拉取项目后运行 `python setup.py` 会恢复运行所需的空配置文件，之后再按实际厂商补充 `provider/`、`provider.env`、`config/config.json`、`config/models.json` 和 `config/api_keys.json`。

---

## 首次恢复

```bash
python setup.py
```

`setup.py` 会在缺失时创建:

| 文件 / 目录 | 默认内容 |
|-------------|----------|
| `provider/` | 空 provider 目录 |
| `provider.env` | 从 `provider.env.example` 复制 |
| `config/config.json` | `{"providers": {}}` |
| `config/models.json` | `{}` |
| `config/api_keys.json` | `{"keys": {}}` |
| `config/global_prompt.md` | 空文件 |

已有文件不会被覆盖。

---

## 鉴权

外部 `/v1/*` 端点全部需要鉴权，在请求头中携带:

```http
Authorization: Bearer <api-key>
```

API Key 在 `config/api_keys.json` 中管理，每个 key 可配置模型白名单和配额限制。

常见错误码:

| 状态码 | 含义 |
|--------|------|
| `401` | 密钥缺失或不存在 |
| `403` | 密钥已禁用或模型不在白名单 |
| `429` | 超出配额 |

---

## 外部 API

### POST /v1/chat/completions

OpenAI 兼容的对话 / 视觉入口。支持 `stream`、`tools`、`response_format`，具体能力取决于模型配置。

```bash
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-client-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "your-provider-your-model-chat",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 200,
    "stream": false
  }'
```

模型必须在 `config/models.json` 中暴露，并包含 `chat` 或 `vision.*` capability。

### POST /v1/audio/speech

OpenAI TTS 兼容格式。返回音频二进制流。

```bash
curl -X POST http://127.0.0.1:8741/v1/audio/speech \
  -H "Authorization: Bearer sk-your-client-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "your-provider-your-model-tts",
    "input": "你好世界",
    "voice": "default",
    "response_format": "mp3",
    "speed": 1.0
  }' --output output.mp3
```

模型必须包含 `audio.tts` capability。

### POST /v1/audio/transcriptions

OpenAI transcription 兼容格式。使用 `multipart/form-data` 上传音频。

```bash
curl -X POST http://127.0.0.1:8741/v1/audio/transcriptions \
  -H "Authorization: Bearer sk-your-client-key" \
  -F "file=@audio.wav" \
  -F "model=your-provider-your-model-asr" \
  -F "language=zh"
```

模型必须包含 `audio.asr` capability。

### POST /v1/images/edits

OpenAI images edit 兼容格式。使用 `multipart/form-data` 上传图片。

```bash
curl -X POST http://127.0.0.1:8741/v1/images/edits \
  -H "Authorization: Bearer sk-your-client-key" \
  -F "image=@photo.png" \
  -F "prompt=变成黑白风格" \
  -F "model=your-provider-your-model-image-edit" \
  -F "response_format=url"
```

模型必须包含 `image.edit` capability。

### 预留端点

以下端点只有在注册对应 capability 的 provider 后才可用:

| 端点 | capability |
|------|------------|
| `POST /v1/images/generations` | `image.generation` |
| `POST /v1/embeddings` | `embedding` |
| `POST /v1/rerank` | `rerank` |
| `POST /v1/videos/generations` | `video.*` |
| `GET /v1/videos/{job_id}` | `video.*` |
| `GET /v1/videos/{job_id}/content` | `video.*` |

---

## 管理 API

管理 API 供 Web 面板调用。默认仓库恢复后 provider 和模型均为空。

### GET /api/health

```bash
curl http://127.0.0.1:8741/api/health
```

默认空配置示例:

```json
{
  "health_score": 70,
  "providers_online": 0,
  "providers_total": 0,
  "models_exposed": 0,
  "models_visible": 0,
  "error_rate_pct": 0.0,
  "server_version": "0.1.0",
  "quota_enabled": true,
  "base_url": "127.0.0.1:8741"
}
```

### GET /api/stats

```bash
curl "http://127.0.0.1:8741/api/stats?period=today"
```

`period` 可选: `today` / `7d` / `30d`。

### GET /api/providers

```bash
curl http://127.0.0.1:8741/api/providers
```

默认返回:

```json
{
  "providers": []
}
```

### POST /api/providers/{name}/toggle

```bash
curl -X POST http://127.0.0.1:8741/api/providers/your-provider/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### GET /api/models

```bash
curl http://127.0.0.1:8741/api/models
```

默认返回:

```json
{
  "models": []
}
```

模型配置示例:

```json
{
  "your-provider-your-model-chat": {
    "provider": "your-provider",
    "model": "your-model-chat",
    "capabilities": ["chat"],
    "endpoint": "/v1/chat/completions",
    "enabled": true,
    "visible": true
  }
}
```

### POST /api/models/{model_id}/toggle

```bash
curl -X POST http://127.0.0.1:8741/api/models/your-provider-your-model-chat/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### POST /api/models/{model_id}/test

```bash
curl -X POST http://127.0.0.1:8741/api/models/your-provider-your-model-chat/test
```

### GET /api/keys

```bash
curl http://127.0.0.1:8741/api/keys
```

默认返回:

```json
{
  "keys": []
}
```

API Key 配置示例:

```json
{
  "keys": {
    "sk-your-client-key": {
      "name": "客户端密钥",
      "enabled": true,
      "models": ["your-provider-your-model-chat"],
      "quota": {
        "total_tokens": 1000000,
        "used_tokens": 0
      }
    }
  }
}
```

### POST /api/keys/{key_id}/models

```bash
curl -X POST http://127.0.0.1:8741/api/keys/sk-your-client-key/models \
  -H "Content-Type: application/json" \
  -d '{"models": ["your-provider-your-model-chat"]}'
```

### GET /api/logs

```bash
curl "http://127.0.0.1:8741/api/logs?status=error&limit=20&q=your-provider"
```

参数:

| 参数 | 说明 |
|------|------|
| `status` | `all` / `ok` / `error` |
| `q` | 搜索关键词 |
| `date` | 日期，默认今日 |
| `limit` | 条数，默认 50 |

### GET /api/usage

```bash
curl "http://127.0.0.1:8741/api/usage?period=today"
```

`period` 可选: `today` / `7d` / `30d`。

### GET /api/config

```bash
curl http://127.0.0.1:8741/api/config
```

返回 `config.json`、`models.json`、`api_keys.json`、`global_prompt.md`、`provider.env` 的当前内容。

### POST /api/config/{file}

```bash
curl -X POST http://127.0.0.1:8741/api/config/models \
  -H "Content-Type: application/json" \
  -d '{"content": {}}'
```

`file` 取值:

| file | 写入目标 |
|------|----------|
| `config` | `config/config.json` |
| `models` | `config/models.json` |
| `api_keys` | `config/api_keys.json` |
| `global_prompt` | `config/global_prompt.md` |
| `provider_env` | `provider.env` |

保存后会自动重载相关模块。

---

## Capability 总览

| Capability | 对应端点 |
|------------|----------|
| `chat` | `/v1/chat/completions` |
| `vision.image` | `/v1/chat/completions` |
| `vision.video` | `/v1/chat/completions` |
| `audio.tts` | `/v1/audio/speech` |
| `audio.asr` | `/v1/audio/transcriptions` |
| `audio.speech_to_speech` | 预留 |
| `image.generation` | `/v1/images/generations` |
| `image.edit` | `/v1/images/edits` |
| `video.*` | `/v1/videos/generations` |
| `embedding` | `/v1/embeddings` |
| `rerank` | `/v1/rerank` |

---

## 错误格式

所有 `/v1/*` 端点统一返回:

```json
{
  "error": {
    "message": "model 'xxx' does not support image.generation",
    "type": "capability_mismatch",
    "code": 400
  }
}
```

常见错误类型: `capability_mismatch` / `auth_error` / `quota_exceeded` / `provider_error` / `invalid_request`。
