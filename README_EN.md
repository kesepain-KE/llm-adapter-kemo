# Kemo LLM Adapter

> Multi-provider LLM unified adapter — One API to access multiple LLM models

Kemo LLM Adapter is a lightweight API gateway that unifies multiple LLM providers (DeepSeek, StepFun, MiniMax, etc.) behind a single **OpenAI-compatible interface**. With one endpoint and one API key, you can switch between different models from different vendors.

---

## Table of Contents

- [Background](#background)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Developing a New Provider](#developing-a-new-provider)
- [FAQ](#faq)
- [License](#license)

---

## Background

As the LLM ecosystem grows, each provider offers its own API format, authentication method, and parameter conventions. Integrating multiple providers requires clients to maintain a lot of adapter logic, making model switching expensive and error-prone.

Kemo LLM Adapter solves this by exposing all providers through a **unified OpenAI-compatible API**. Clients only need to talk to one endpoint and change the model name to switch between backends.

## Features

- **Unified API** — All providers use the OpenAI-compatible `/v1/chat/completions` endpoint
- **Streaming** — SSE streaming with usage in the final chunk
- **Pluggable Providers** — Each provider lives in its own directory, auto-discovered by the registry
- **API Key Management** — Per-key model whitelist + token quota control
- **Usage Analytics** — Every request logged as JSONL, aggregated by key/provider/model
- **Hot-Reload Config** — `config.json`, `models.json`, `api_keys.json` changes take effect without restart
- **Web Dashboard** — Manage providers, models, and keys from your browser
- **Provider Scaffolding** — `add_diy.scaffold()` generates adapter boilerplate in one call
- **Docker Support** — Ready-to-use Docker Compose setup

## Architecture

```
kemo-llm-adapter/
├── config/                  # Global configuration (hot-reload)
│   ├── config.json          # Provider enable/disable switches
│   ├── models.json          # Exposed model name → provider+model mapping
│   ├── api_keys.json        # Client keys + whitelist + quota
│   └── global_prompt.md     # Global system prompt
│
├── provider/<name>/         # Each provider in its own directory
│   ├── model.json           # Metadata (base_url, api_key_env, model list)
│   ├── __init__.py          # Exports adapter classes + factory functions
│   ├── chat.py              # Chat adapter (invoke + invoke_stream)
│   ├── token_count.py       # Token counting & normalization
│   ├── audio.py             # Audio adapter (optional)
│   ├── image.py             # Image adapter (optional)
│   └── ...                  # Other capability modules
│
├── core/                    # Orchestration layer
│   ├── registry.py          # Scans provider/*/model.json, loads modules
│   ├── router.py            # Resolves model names to provider+model
│   ├── auth.py              # Bearer token auth + model whitelist
│   ├── call_log.py          # Unified request logging (JSON Lines)
│   └── usage.py             # Token usage & quota management
│
├── api/                     # FastAPI service layer
│   ├── app.py               # Application factory
│   ├── routes/              # Routes (v1.py main chat + admin endpoints)
│   └── services/            # Business logic
│
├── add_diy/                 # Toolkit
│   ├── scaffold.py          # Generates new provider boilerplate
│   └── test.py              # Minimal connectivity test
│
├── web/                     # Web dashboard frontend
├── server.py                # Entry point
├── docker-compose.yml       # Docker deployment
├── Dockerfile               # Image build
└── requirements.txt         # Python dependencies
```

### Core Conventions

| Convention | Description |
|------------|-------------|
| Model naming | `{provider}-{vendor_model}`, e.g. `deepseek-deepseek-v4-flash` |
| Provider isolation | Each provider directory is completely isolated — no cross-imports |
| Request/response format | Always OpenAI-compatible |
| Key source | Providers read API keys from environment variables |

## Quick Start

### Prerequisites

- Python >= 3.10
- pip

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/kemo-llm-adapter.git
cd kemo-llm-adapter

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create configuration files
cp provider.env.example provider.env
cp config/api_keys.json.example config/api_keys.json
cp config/models.json.example config/models.json

# 4. Edit provider.env and fill in your API keys
# 5. Edit api_keys.json to set up your internal keys

# 6. Start the server
python server.py
```

The server runs at `http://127.0.0.1:8741` by default.

### Docker Deployment

```bash
# Make sure provider.env is configured
docker-compose up -d
```

### Verify the Service

```bash
# Health check
curl http://127.0.0.1:8741/health

# List available models (requires a valid key)
curl -H "Authorization: Bearer sk-your-key" http://127.0.0.1:8741/v1/models

# Test chat
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "deepseek-deepseek-v4-flash", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Configuration

### Configuration Files

| File | Purpose | Hot-Reload |
|------|---------|------------|
| `config/config.json` | Provider enable/disable | ✅ |
| `config/models.json` | Model name mapping | ✅ |
| `config/api_keys.json` | Client keys + whitelist + quota | ✅ |
| `config/global_prompt.md` | Global system prompt | ✅ |
| `provider/*/model.json` | Provider metadata | ❌ Restart needed |
| `provider.env` | Provider API keys | ❌ Restart needed |

### Configuration Examples

**config.json** — Control which providers are active:

```json
{
  "providers": {
    "deepseek": { "enabled": true },
    "stepfun": { "enabled": true }
  }
}
```

**models.json** — Register exposed models:

```json
{
  "deepseek-deepseek-v4-flash": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "capability": "chat",
    "enabled": true,
    "visible": true
  }
}
```

**api_keys.json** — Define client keys and permissions:

```json
{
  "keys": {
    "sk-kemo-admin": {
      "name": "Admin Key",
      "enabled": true,
      "models": ["deepseek-deepseek-v4-flash"],
      "quota": { "total_tokens": 1000000000, "used_tokens": 0 }
    }
  }
}
```

**provider.env** — Provider API keys:

```env
DEEPSEEK_API_KEY=sk-your-real-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
STEPFUN_API_KEY=your-stepfun-key
STEPFUN_BASE_URL=https://api.stepfun.com
```

## API Endpoints

| Method | Path | Description | Auth Required |
|--------|------|-------------|---------------|
| `GET` | `/` | Web dashboard | No |
| `GET` | `/health` | Health check | No |
| `GET` | `/v1/models` | List visible models | Yes |
| `POST` | `/v1/chat/completions` | Chat completion (streaming + non-streaming) | Yes |
| `GET` | `/api/providers` | Provider status list | Yes |
| `POST` | `/api/providers/{name}/toggle` | Enable/disable provider | Yes |
| `GET` | `/api/models` | Model list (including hidden) | Yes |
| `POST` | `/api/models/{id}/toggle` | Enable/disable model | Yes |
| `POST` | `/api/models/{id}/test` | Model connectivity test | Yes |
| `GET` | `/api/keys` | Key list | Yes |
| `POST` | `/api/keys/{id}/models` | Update key model whitelist | Yes |
| `GET` | `/api/logs` | Call logs | Yes |
| `GET` | `/api/usage` | Usage statistics | Yes |
| `GET` | `/api/config` | View configuration | Yes |
| `POST` | `/api/config/{file}` | Save configuration | Yes |

### Chat Request Example

```bash
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-deepseek-v4-flash",
    "messages": [{"role": "user", "content": "Hello"}],
    "temperature": 0.7,
    "max_tokens": 1024,
    "stream": false
  }'
```

## Developing a New Provider

Use the scaffolding tool to generate adapter boilerplate:

```python
from add_diy.scaffold import scaffold

created = scaffold(
    "minimax",
    base_url="https://api.minimax.com",
    vendor_model="abab-v6.5",
    modules=["chat", "token_count", "audio", "image"],
)
```

After generation, you need to:

1. Edit `provider/minimax/chat.py` — implement parameter mapping and response normalization
2. Edit `config/config.json` — enable the new provider
3. Edit `config/models.json` — register models
4. Edit `config/api_keys.json` — grant model permissions to a key
5. Add the API key to `provider.env`
6. Restart the server

For detailed guidance, refer to `agent_control.md`.

## FAQ

### 401 Unauthorized on startup

The request lacks an `Authorization: Bearer` header, or the key is not in `api_keys.json`.

### Config changes not taking effect

- `config/config.json`, `models.json`, `api_keys.json` → hot-reload, no restart needed
- `provider/*/model.json`, `provider.env` → restart required

### How to temporarily disable a model?

Set `"enabled": false` for that model in `models.json`. No restart needed.

### How to add a new provider?

Use `add_diy.scaffold()` to generate boilerplate, then follow the steps in `agent_control.md`.

---

## License

[MIT](LICENSE) © 2025 Kemo LLM Adapter Contributors
