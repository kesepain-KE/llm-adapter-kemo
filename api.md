# Kemo LLM Adapter — API 文档

服务地址 `http://127.0.0.1:8741`。

---

## 鉴权

外部 `/v1/*` 端点全部需要鉴权。在请求头中携带：

```
Authorization: Bearer <api-key>
```

API Key 在 `config/api_keys.json` 中管理，每个 key 有模型白名单和配额限制。

错误码：
- `401` — 密钥缺失或不存在
- `403` — 密钥已禁用或模型不在白名单
- `429` — 超出配额

---

## 外部 API（智能体 / 客户端调用）

### POST /v1/chat/completions — 对话 / 视觉

OpenAI 兼容格式。支持 `stream`、`tools`、`response_format`。

```bash
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-kemo-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-deepseek-v4-flash",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 200,
    "stream": false
  }'
```

可用模型（`chat` / `vision.*` 能力）：

| 模型 ID | 厂商模型 | 能力 | 模态 |
|---------|---------|------|------|
| `deepseek-deepseek-v4-flash` | deepseek-v4-flash | chat | 文本 |
| `deepseek-deepseek-v4-pro` | deepseek-v4-pro | chat | 文本 |
| `stepfun-step-3.7-flash` | step-3.7-flash | chat, vision.image | 文本·图片·视频 |
| `stepfun-step-3.5-flash-2603` | step-3.5-flash-2603 | chat | 文本 |
| `stepfun-step-3.5-flash` | step-3.5-flash | chat | 文本 |
| `stepfun-step-router-v1` | step-router-v1 | chat | 文本 |

**注意**: `/v1/chat/completions` 接受 `chat` 和 `vision.*` 能力的模型，传入仅有 `audio.*` / `image.*` 能力的模型会返回 `400 capability_mismatch`。

---

### POST /v1/audio/speech — 文本转语音 (TTS)

OpenAI TTS 兼容格式。返回音频二进制流。

```bash
curl -X POST http://127.0.0.1:8741/v1/audio/speech \
  -H "Authorization: Bearer sk-kemo-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "stepfun-stepaudio-2.5-tts",
    "input": "你好世界",
    "voice": "cixingnansheng",
    "response_format": "mp3",
    "speed": 1.0
  }' --output output.mp3
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| model | string | 是 | `stepfun-stepaudio-2.5-tts` |
| input | string | 是 | 合成文本，最大 1000 字符 |
| voice | string | 是 | 音色名称 |
| response_format | string | 否 | `mp3`(默认) / `wav` / `flac` / `opus` / `pcm` |
| speed | float | 否 | 语速 0.5~2.0，默认 1.0 |

**Content-Type**: 根据 `response_format` 返回对应 MIME 类型。

---

### POST /v1/audio/transcriptions — 语音转文字 (ASR)

OpenAI transcription 兼容格式。multipart/form-data 上传。

```bash
curl -X POST http://127.0.0.1:8741/v1/audio/transcriptions \
  -H "Authorization: Bearer sk-kemo-admin" \
  -F "file=@audio.wav" \
  -F "model=stepfun-stepaudio-2.5-asr" \
  -F "language=zh"
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 音频文件 (wav/mp3/ogg/pcm) |
| model | string | 是 | `stepfun-stepaudio-2.5-asr` |
| language | string | 否 | 语言，默认 `zh` |

**返回**:

```json
{
  "text": "识别出的文本",
  "model": "stepaudio-2.5-asr"
}
```

---

### POST /v1/images/edits — 图像编辑

OpenAI images.edit 兼容格式。multipart/form-data 上传。

```bash
curl -X POST http://127.0.0.1:8741/v1/images/edits \
  -H "Authorization: Bearer sk-kemo-admin" \
  -F "image=@photo.png" \
  -F "prompt=变成黑白风格" \
  -F "model=stepfun-step-image-edit-2" \
  -F "response_format=url"
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| image | file | 是 | 输入图片 (jpg/png/webp) |
| prompt | string | 是 | 编辑描述，最大 512 字符 |
| model | string | 是 | `stepfun-step-image-edit-2` |
| response_format | string | 否 | `url`(默认) / `b64_json` |

**返回**:

```json
{
  "created": 1589478378,
  "data": [
    {
      "url": "https://...",
      "finish_reason": "success",
      "seed": 123838
    }
  ]
}
```

---

### POST /v1/images/generations — 文生图

```
预留端点。当前未注册 image.generation 模型，调用返回 503。
```

```bash
curl -X POST http://127.0.0.1:8741/v1/images/generations \
  -H "Authorization: Bearer sk-kemo-admin" \
  -H "Content-Type: application/json" \
  -d '{"model": "...", "prompt": "...", "n": 1, "size": "1024x1024"}'
```

---

### POST /v1/embeddings — 文本嵌入

```
预留端点。当前未注册 embedding 模型，调用返回 503。
```

```bash
curl -X POST http://127.0.0.1:8741/v1/embeddings \
  -H "Authorization: Bearer sk-kemo-admin" \
  -H "Content-Type: application/json" \
  -d '{"model": "...", "input": "text to embed"}'
```

---

### POST /v1/rerank — 文档重排

```
预留端点。当前未注册 rerank 模型，调用返回 503。
```

```bash
curl -X POST http://127.0.0.1:8741/v1/rerank \
  -H "Authorization: Bearer sk-kemo-admin" \
  -H "Content-Type: application/json" \
  -d '{"model": "...", "query": "search query", "documents": ["doc1", "doc2"], "top_n": 3}'
```

---

### POST /v1/videos/generations — 视频生成

```
预留端点。当前未实现 video adapter，调用返回 503。
```

```bash
curl -X POST http://127.0.0.1:8741/v1/videos/generations \
  -H "Authorization: Bearer sk-kemo-admin" \
  -H "Content-Type: application/json" \
  -d '{"model": "...", "prompt": "..."}'
```

---

### GET /v1/videos/{job_id} — 查询视频任务

```
预留端点。查询异步视频任务状态。
```

### GET /v1/videos/{job_id}/content — 下载视频结果

```
预留端点。下载完成的视频文件。
```

---

## 管理 API（项目面板调用，无需鉴权）

### GET /api/health — 健康检查

```bash
curl http://127.0.0.1:8741/api/health
```

```json
{
  "health_score": 100,
  "providers_online": 2,
  "providers_total": 2,
  "models_exposed": 9,
  "models_visible": 9,
  "error_rate_pct": 0.0,
  "server_version": "0.1.0",
  "quota_enabled": true,
  "base_url": "http://127.0.0.1:8741"
}
```

---

### GET /api/stats — 仪表盘统计

```bash
curl "http://127.0.0.1:8741/api/stats?period=today"
```

参数: `period` = `today` / `7d` / `30d`

---

### GET /api/providers — Provider 列表

```bash
curl http://127.0.0.1:8741/api/providers
```

```json
{
  "providers": [
    {
      "name": "stepfun",
      "enabled": true,
      "base_url": "https://api.stepfun.com",
      "modules": ["chat", "token_count", "audio", "image"],
      "capabilities": ["chat", "audio", "image", "token_count"],
      "models": ["step-3.7-flash", "stepaudio-2.5-tts", "stepaudio-2.5-asr", "step-image-edit-2", ...]
    }
  ]
}
```

---

### POST /api/providers/{name}/toggle — 启用/禁用 Provider

```bash
curl -X POST http://127.0.0.1:8741/api/providers/stepfun/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

### GET /api/models — 模型路由表

```bash
curl http://127.0.0.1:8741/api/models
```

```json
{
  "models": [
    {
      "id": "stepfun-step-3.7-flash",
      "provider": "stepfun",
      "model": "step-3.7-flash",
      "capabilities": ["chat", "vision.image"],
      "capability": "chat",
      "endpoint": "/v1/chat/completions",
      "enabled": true,
      "visible": true,
      "modalities": ["text", "image", "video"]
    }
  ]
}
```

---

### POST /api/models/{model_id}/toggle — 启用/禁用模型

```bash
curl -X POST http://127.0.0.1:8741/api/models/stepfun-step-3.7-flash/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

### POST /api/models/{model_id}/test — 模型连通测试

```bash
curl -X POST http://127.0.0.1:8741/api/models/stepfun-step-3.7-flash/test
```

```json
{
  "ok": true,
  "capability": "chat",
  "endpoint": "/v1/chat/completions",
  "latency_ms": 428.3,
  "message": "ok",
  "error": null,
  "content": "pong"
}
```

失败时:
```json
{
  "ok": false,
  "capability": "audio.tts",
  "endpoint": "/v1/audio/speech",
  "message": "StepFunAudioAPIError: ...",
  "error": "StepFunAudioAPIError: ..."
}
```

不同 capability 使用不同的测试策略：
- `chat` / `vision.*` → ping 消息
- `audio.tts` → 短文本合成
- `audio.asr` → 内置极短 WAV 识别
- `image.edit` → 内置 1x1 PNG 编辑
- `embedding` / `rerank` → 返回 `not implemented`
- `video.*` → dry-run 确认

---

### GET /api/keys — API 密钥列表

```bash
curl http://127.0.0.1:8741/api/keys
```

```json
{
  "keys": [
    {
      "id": "sk-kemo-admin",
      "name": "管理密钥",
      "enabled": true,
      "models": ["deepseek-deepseek-v4-flash", "stepfun-step-3.7-flash", ...],
      "quota": {"total_tokens": 1000000000, "used_tokens": 26}
    }
  ]
}
```

---

### POST /api/keys/{key_id}/models — 更新密钥模型白名单

```bash
curl -X POST http://127.0.0.1:8741/api/keys/sk-kemo-admin/models \
  -H "Content-Type: application/json" \
  -d '{"models": ["deepseek-deepseek-v4-flash", "stepfun-step-3.7-flash"]}'
```

---

### GET /api/logs — 调用日志

```bash
curl "http://127.0.0.1:8741/api/logs?status=error&limit=20&q=stepfun"
```

参数: `status` = `all` / `ok` / `error`、`q` = 搜索关键词、`date` = 日期 (默认今日)、`limit` = 条数 (默认 50)

---

### GET /api/usage — 用量统计

```bash
curl "http://127.0.0.1:8741/api/usage?period=today"
```

参数: `period` = `today` / `7d` / `30d`

```json
{
  "period": "today",
  "request_count": 42,
  "total_tokens": 123456,
  "latency": {"p50_ms": 234.5, "p95_ms": 890.1, "p99_ms": 1200.3}
}
```

---

### GET /api/config — 读取全部配置

```bash
curl http://127.0.0.1:8741/api/config
```

返回 `config.json`、`models.json`、`api_keys.json`、`global_prompt.md`、`provider.env` 全部内容。

---

### POST /api/config/{file} — 保存配置文件

```bash
curl -X POST http://127.0.0.1:8741/api/config/models \
  -H "Content-Type: application/json" \
  -d '{"content": {...}}'
```

`file` 取值: `config` / `models` / `api_keys` / `global_prompt` / `provider_env`。

保存后自动重载相关模块（Router / Registry / Auth）。

---

## 能力分类总览

| Capability | 对应端点 | 已注册模型 |
|-----------|---------|-----------|
| `chat` | `/v1/chat/completions` | deepseek×2, stepfun×4 |
| `vision.image` | `/v1/chat/completions` | stepfun×1 (step-3.7-flash) |
| `vision.video` | `/v1/chat/completions` | — |
| `audio.tts` | `/v1/audio/speech` | stepfun×1 |
| `audio.asr` | `/v1/audio/transcriptions` | stepfun×1 |
| `audio.speech_to_speech` | (预留) | — |
| `image.generation` | `/v1/images/generations` | — |
| `image.edit` | `/v1/images/edits` | stepfun×1 |
| `video.*` | `/v1/videos/generations` | — |
| `embedding` | `/v1/embeddings` | — |
| `rerank` | `/v1/rerank` | — |

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

错误类型: `capability_mismatch` / `auth_error` / `quota_exceeded` / `provider_error` / `invalid_request`。
