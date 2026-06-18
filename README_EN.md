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
- [Contributing](#contributing)
- [License](#license)

---

## Background

As the LLM ecosystem grows, each provider offers its own API format, authentication method, and parameter conventions. Integrating multiple providers requires clients to maintain extensive adapter logic, making model switching expensive and error-prone.

Kemo LLM Adapter solves this by exposing all providers through a **unified OpenAI-compatible API**. Clients only need to talk to one endpoint and change the model name to switch between backends.

## Features

- **Unified API** — All providers share the OpenAI-compatible `/v1/chat/completions` endpoint
- **Streaming** — SSE streaming with usage metadata in the final chunk
- **Pluggable Providers** — Each provider lives in its own directory, auto-discovered by the registry
- **API Key Management** — Per-key model whitelist + token quota control
- **Usage Analytics** — JSONL request logging, aggregated by key/provider/model
- **Hot-Reload Config** — `config.json`, `models.json`, `api_keys.json` reload without restart
- **Web Dashboard** — Manage providers, models, and keys from your browser
- **Provider Scaffolding** — `add_diy.scaffold()` generates adapter boilerplate in one call
- **Docker Support** — Ready-to-use Docker Compose setup
- **AI Agent Friendly** — `agent_control.md` guides AI agents to configure providers autonomously

## Architecture

```
kemo-llm-adapter/
├── config/                  # Global configuration (hot-reload)
│   ├── config.json          # Provider enable/disable switches
│   ├── models.json          # Exposed model name → provider+model mapping
│   ├── api_keys.json        # Client keys + whitelist + quota
│   └── global_prompt.md     # Global system prompt
│
## Quick Start

### Prerequisites

- Python >= 3.10
- pip

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/kesepain-KE/llm-adapter-kemo.git
cd llm-adapter-kemo

# 2. Run the initialization wizard (env check → dir init → deps install → core validation)
python setup.py
```

The wizard checks Python version, detects dependencies (prompts to install if missing), creates required directories, and validates core modules. Use `python setup.py --check` for a quick environment check only.

### Configuration

```bash
# Copy and edit example config files
cp provider.env.example provider.env
cp config/api_keys.json.example config/api_keys.json
cp config/models.json.example config/models.json
```

Then configure provider API keys using one of the following approaches:

**Option A — Let an AI Agent handle it (recommended)**
```bash
# Have your AI assistant read agent_control.md and complete the setup automatically
```

**Option B — Manual editing**
- `provider.env` — Fill in each provider's API keys
- `config/api_keys.json` — Set up internal keys and quotas
- `config/models.json` — Register models to expose

### Launch

```bash
python server.py
```

The server runs at `http://127.0.0.1:8741` by default.
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

### Installation & Launch

```bash
# 1. Clone the repository
git clone https://github.com/kesepain-KE/llm-adapter-kemo.git
cd llm-adapter-kemo

# 2. One-step initialization (env check + deps install + dir init + core validation)
python setup.py

# 3. Edit provider.env with your API keys
# 4. Edit config/api_keys.json to set up internal keys

# 5. Start the server
python server.py
```

The server runs at `http://127.0.0.1:8741` by default.

> `setup.py` is the recommended entry point for new users. It handles environment checks, dependency installation, directory creation, and core module validation in a guided wizard. Use `python setup.py --check` for a quick environment check only.

### Docker Deployment

```bash
docker-compose up -d
```

### Verify the Service

```bash
# Health check
curl http://127.0.0.1:8741/health

# List available models
curl -H "Authorization: Bearer sk-your-key" http://127.0.0.1:8741/v1/models

# Test chat
curl -X POST http://127.0.0.1:8741/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "deepseek-deepseek-v4-flash", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Configuration

| File | Purpose | Hot-Reload |
|------|---------|------------|
| `config/config.json` | Provider enable/disable | ✅ |
| `config/models.json` | Model name mapping | ✅ |
| `config/api_keys.json` | Client keys + whitelist + quota | ✅ |
| `config/global_prompt.md` | Global system prompt | ✅ |
| `provider/*/model.json` | Provider metadata | ❌ Restart needed |
| `provider.env` | Provider API keys | ❌ Restart needed |

See `provider.env.example` and example files under `config/` for detailed configuration templates.

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

After generation:

1. Edit `provider/minimax/chat.py` — implement parameter mapping and response normalization
2. Register the model in `config/models.json`, `api_keys.json`, and `provider.env`
3. Restart the server

For detailed guidance, refer to `agent_control.md`.

## FAQ

### 401 Unauthorized on startup

Missing `Authorization: Bearer` header, or the key is not registered in `api_keys.json`.

### Config changes not taking effect

- JSON files under `config/` → hot-reload, no restart needed
- `provider/*/model.json`, `provider.env` → restart required

### How to temporarily disable a model?

Set `"enabled": false` for that model in `models.json`. No restart needed.

### How to add a new provider?

Use `add_diy.scaffold()` to generate boilerplate, then follow `agent_control.md`.

## Contributing

PRs and Issues are welcome. The `agent_control.md` manual is designed to guide AI agents through provider development and configuration management autonomously.

## License

[MIT](LICENSE) © 2025 Kemo LLM Adapter Contributors
