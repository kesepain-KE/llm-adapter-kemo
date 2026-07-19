# VOTX LLM Adapter

<p align="center">
  <img src="./llm-adapter-votx.png" alt="VOTX LLM Adapter" width="300">
</p>

> Multi-provider LLM unification layer — one OpenAI-compatible API to rule them all

---

## Overview

VOTX LLM Adapter is a lightweight API gateway that unifies DeepSeek, StepFun, and other LLM providers behind a single **OpenAI-compatible API**. It acts as a middleware layer — your existing OpenAI SDK clients just change the base URL and API key, then switch between providers by modifying the `model` parameter.

## Quick Setup

```bash
git clone https://github.com/kesepain-KE/llm-adapter-votx.git
cd llm-adapter-votx
python setup.py          # Install dependencies & generate config templates
# Edit provider.env with your API keys, then:
python server.py         # Start the gateway on http://127.0.0.1:8741
```

### Prerequisites

- Python >= 3.10
- pip
- Node.js >= 20 & npm (needed for web panel builds and update.py)

### Building the Admin Panel (Optional)

```bash
cd web && npm install && npm run build && cd ..
```

`python update.py` will also run this step after an update.

## How It Works

```
Your App / AI Agent
       │
       ▼  (OpenAI-compatible SDK)
 ┌─────────────────┐
 │  VOTX Gateway   │  ← one endpoint, one API key
 │  :8741          │
 └────────┬────────┘
       │
       ├── DeepSeek API
       ├── StepFun API
       └── (more providers...)
```

## Key Concepts

| Concept | What it means |
|---------|--------------|
| **Model ID** | Format: `{provider}-{vendor_model}`, e.g. `deepseek-deepseek-v4-flash` |
| **Provider** | A plugin module handling API translation for one vendor |
| **Admin Panel** | React Web UI at `http://127.0.0.1:8741/` for managing keys, models, logs |
| **Hot-reload** | Config changes in `config/` take effect without restarting the server |
| **Key Management** | Per-key model whitelist + token quota |
| **Usage Tracking** | JSONL call logs aggregated by key, provider, model, and capability |

## API Endpoints

All endpoints are OpenAI-compatible.

### Base URL

```
http://<your-host>:8741
```

### Authentication

```
Authorization: Bearer sk-your-key
```

### Admin Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/models/{id}/test` | Model connectivity test (availability + response latency) |

In the admin panel, the model test result shows only `availability` and `response latency`, mapped from `ok` and `response_latency_ms`.

### Chat Completions

```
POST /v1/chat/completions
```

Chat completions support both non-streaming and streaming. For streaming calls, the gateway asks the upstream provider to include usage when possible, then records usage and deducts quota after the stream finishes.

```bash
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-deepseek-v4-flash",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | — | Model ID (see `/v1/models`) |
| `messages` | array | — | OpenAI-format message array |
| `temperature` | number | 1.0 | Sampling temperature |
| `top_p` | number | 1.0 | Nucleus sampling |
| `max_tokens` | integer | 4096 | Max generated tokens |
| `stream` | boolean | false | Enable streaming |
| `stop` | string/array | null | Stop sequences |
| `tools` | array | null | Tool/function call definitions |
| `response_format` | object | null | e.g. `{"type": "json_object"}` |

### List Models

```
GET /v1/models
```

### Text-to-Speech

```
POST /v1/audio/speech
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model ID (e.g. `stepfun-stepaudio-2.5-tts`) |
| `input` | string | Text to synthesize (max 1000 chars) |
| `voice` | string | Voice ID (see `provider/*/explain.md`) |
| `response_format` | string | mp3 / wav / flac / opus / pcm |
| `speed` | number | Speed 0.5～2.0 |

### Speech-to-Text

```
POST /v1/audio/transcriptions
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model ID (e.g. `stepfun-stepaudio-2.5-asr`) |
| `file` | file | Audio file (mp3 / wav / ogg etc.) |
| `language` | string | Language code (optional) |

### Image Generation

```
POST /v1/images/generations
```

### Image Editing

```
POST /v1/images/edits
```

Multipart/form-data with `image` file + `prompt` + `model`.

### Embeddings / Rerank / Video Generation

```
POST /v1/embeddings
POST /v1/rerank
POST /v1/videos/generations
GET  /v1/videos/{job_id}
GET  /v1/videos/{job_id}/content
```

Available models depend on registered providers and `models.json` configuration.

## Configuration

| File | Purpose | Hot-reload |
|------|---------|------------|
| `provider.env` | Provider API keys (from environment) | ❌ Restart required |
| `config/config.json` | Provider on/off switches | ✅ |
| `config/models.json` | Exposed model → provider mapping | ✅ |
| `config/api_keys.json` | Client keys + whitelist + quota | ✅ |
| `config/global_prompt.md` | Global system prompt | ✅ |
| `provider/*/model.json` | Provider metadata | ❌ Restart required |

Example configs are available in `.example` copies of each file.

Usage dates are grouped by the application timezone. The default is `Asia/Shanghai`; set `VOTX_TIMEZONE` in the environment or `provider.env` to override it.

### Concurrency, retries, and quota state

Chat calls pass through global and per-provider admission limits before reaching
an upstream provider. These `provider.env` settings require a restart:

| Variable | Default | Purpose |
|----------|---------|---------|
| `VOTX_CHAT_GLOBAL_CONCURRENCY` | `32` | Total active upstream chat calls per process |
| `VOTX_CHAT_PROVIDER_CONCURRENCY` | `16` | Active upstream chat calls per provider |
| `VOTX_CHAT_QUEUE_TIMEOUT` | `10` | Seconds to wait for capacity before returning `429` |
| `VOTX_CONNECT_RETRIES` | `2` | Connection retries allowed only before any upstream chunk |

Mutable `used_tokens` counters are authoritative in
`data_status/quota.sqlite3`, using SQLite WAL and transactional increments.
`config/api_keys.json` continues to hold key identity, model allow-lists, total
quotas, and the one-time migration seed. A normal config save does not replace
live SQLite counters with a stale panel snapshot.

An opt-in streaming load test is included. Run it only against an approved
target; the key is provided through the environment so it is not exposed in the
command line:

```bash
VOTX_LOAD_TEST_API_KEY=sk-votx-... python tests/load_chat.py \
  --model deepseek-deepseek-v4-flash --concurrency 10 --requests 50
```

Admission state is currently process-local, while call logs and configuration
remain file-backed. Do not enable multiple Uvicorn workers until admission and
log/config state have been moved to shared, process-safe storage.

### Model Registration Example

```json
{
  "deepseek-deepseek-v4-flash": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "capabilities": ["chat"],
    "endpoint": "/v1/chat/completions",
    "enabled": true,
    "visible": true
  }
}
```

## Provider Development

### Built-in Providers

| Provider | Module | Capabilities |
|----------|--------|-------------|
| **DeepSeek** | `provider/deepseek/` | chat · token_count |
| **StepFun** | `provider/stepfun/` | chat · token_count · audio (TTS/ASR) · image |

### Provider Onboarding

`add_diy/` currently provides Agent workflow documents, not an importable Python scaffold generator. To add a provider, read `agent_control.md`, then follow `add_diy/build_adapter.md` to manually create `provider/<name>/` and the adapter files.

After creation:
1. Edit `provider/{name}/chat.py` for parameter mapping and response normalization
2. Edit `provider/{name}/token_count.py` so real usage, streaming usage, cache tokens, and reasoning tokens normalize correctly
3. Register in `config/models.json`
4. Configure API key in `provider.env`
5. Restart the service

### Model Naming Convention

```
{provider}-{vendor_model}
```

Example: `deepseek-deepseek-v4-flash` → provider=`deepseek`, vendor_model=`deepseek-v4-flash`

## Project Structure

```
llm-adapter-votx/
├── config/                  # Global configuration (hot-reload)
│   ├── config.json          # Provider on/off switches
│   ├── models.json          # Model → provider mapping
│   ├── api_keys.json        # Client keys + whitelist + quota
│   └── global_prompt.md     # Global safety prompt
│
├── provider/<name>/         # Each provider in its own directory
│   ├── model.json           # Provider metadata
│   ├── chat.py              # Chat adapter
│   ├── token_count.py       # Token counting
│   ├── audio.py             # Audio adapter (optional)
│   └── image.py             # Image adapter (optional)
│
├── core/                    # Orchestration layer
│   ├── __init__.py          # bootstrap() + AppContext
│   ├── registry.py          # Auto-discover & load providers
│   ├── router.py            # Model → provider resolution
│   ├── auth.py              # Bearer auth + model whitelist
│   ├── call_log.py          # Call logging (JSONL)
│   └── usage.py             # Token usage + quota deduction
│
├── api/                     # FastAPI service layer
│   ├── app.py               # App entry
│   ├── routes/              # Route handlers
│   ├── services/            # Business logic
│   └── utils/               # Utilities
│
├── add_diy/                 # Provider onboarding and key creation workflow docs
├── web/                     # React/Vite admin panel
├── server.py                # Service entry point
├── setup.py                 # Setup wizard
├── update.py                # Git update script (auto-backup, frontend rebuild)
├── requirements.txt         # Python dependencies
├── version.json             # Version number
└── agent_control.md         # AI Agent operation manual
```

## Updating

```bash
python update.py            # Interactive update
python update.py --check    # Check version only
python update.py --yes      # Non-interactive update
```

The update script automatically backs up `config/` and `provider.env`, pulls the latest code, restores your configuration, and when needed installs Python dependencies and rebuilds the web panel.

## Related Projects

- [VOTX Agent](https://github.com/kesepain-KE/votx-agent) — Multi-user AI Agent framework

## License

[MIT](LICENSE) © 2025 VOTX LLM Adapter Contributors
