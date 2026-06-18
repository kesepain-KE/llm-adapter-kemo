# Kemo LLM Adapter

> Multi-provider LLM unified adapter — One API to access multiple LLM models

Kemo LLM Adapter is a lightweight API gateway that unifies multiple LLM providers (DeepSeek, StepFun, MiniMax, etc.) behind a single **OpenAI-compatible interface**. With one endpoint and one API key, you can switch between different models from different vendors.

---

## Table of Contents

- [Background](#background)
- [Installation](#installation)
- [Usage](#usage)
- [Architecture](#architecture)
- [Related Projects](#related-projects)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

---

## Background

As the LLM ecosystem grows, each provider offers its own API format, authentication method, and parameter conventions. Integrating multiple providers requires clients to maintain extensive adapter logic, making model switching expensive and error-prone.

Kemo LLM Adapter solves this by exposing all providers through a **unified OpenAI-compatible API**. Clients only need to talk to one endpoint and change the model name to switch between backends.

### Features

- Unified API — All providers share the OpenAI-compatible `/v1/chat/completions` endpoint, supporting both streaming and non-streaming
- Pluggable Providers — Each provider lives in its own directory, auto-discovered by the registry. No framework code changes needed to add new providers
- API Key Management — Per-key model whitelist + token quota control
- Usage Analytics — JSONL request logging, aggregated by key, provider, or model
- Hot-Reload Config — `config.json`, `models.json`, `api_keys.json` reload without restart
- Web Dashboard — Manage providers, models, and keys from your browser
- Provider Scaffolding — `add_diy.scaffold()` generates adapter boilerplate in one call
- Docker Support — Ready-to-use Docker Compose setup
- AI Agent Friendly — `agent_control.md` guides AI agents to configure providers autonomously

## Installation

### Prerequisites

- Python >= 3.10
- pip

### Get the Project

```bash
git clone https://github.com/kesepain-KE/llm-adapter-kemo.git
cd llm-adapter-kemo
```

### Initialize

```bash
python setup.py
```

`setup.py` is the initialization wizard. It runs Python version checks, dependency detection (prompts to install if missing), creates required directories (`data_status/call_log/` and `provider/`), and validates core modules. Use `python setup.py --check` for a quick environment check, `--install` for dependency installation only, or `--validate` for core validation only.

### Configuration

```bash
# Copy example config files
cp provider.env.example provider.env
cp config/api_keys.json.example config/api_keys.json
cp config/models.json.example config/models.json
```

Two approaches to configure provider API keys:

**Option A — Let an AI Agent handle it (recommended)**
Have your AI assistant read `agent_control.md` and complete the provider setup automatically.

**Option B — Manual editing**
- `provider.env` — Fill in each provider's API keys
- `config/api_keys.json` — Set up internal keys and quotas
- `config/models.json` — Register models to expose

### Launch

```bash
python server.py
```

The server runs at `http://127.0.0.1:8741` by default.

### Docker Deployment

```bash
docker-compose up -d
```

## Usage

### Configuration

| File | Purpose | Hot-Reload |
|------|---------|------------|
| `config/config.json` | Provider enable/disable | ✅ |
| `config/models.json` | Model name mapping | ✅ |
| `config/api_keys.json` | Client keys + whitelist + quota | ✅ |
| `config/global_prompt.md` | Global system prompt | ✅ |
| `provider/*/model.json` | Provider metadata | ❌ Restart needed |
| `provider.env` | Provider API keys | ❌ Restart needed |

See `provider.env.example` and `.example` files under `config/` for detailed templates.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web dashboard |
| `GET` | `/health` | Health check |
| `GET` | `/v1/models` | List visible models |
| `POST` | `/v1/chat/completions` | Chat completion (streaming + non-streaming) |
| `GET` | `/api/providers` | Provider status list |
| `POST` | `/api/providers/{name}/toggle` | Enable/disable provider |
| `GET` | `/api/models` | Model list (including hidden) |
| `POST` | `/api/models/{id}/toggle` | Enable/disable model |
| `POST` | `/api/models/{id}/test` | Model connectivity test |
| `GET` | `/api/keys` | Key list |
| `POST` | `/api/keys/{id}/models` | Update key model whitelist |
| `GET` | `/api/logs` | Call logs |
| `GET` | `/api/usage` | Usage statistics |
| `GET` | `/api/config` | View configuration |
| `POST` | `/api/config/{file}` | Save configuration |

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

### Developing a New Provider

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
│   ├── model.json           # Metadata (base_url, api_key_env, etc.)
│   ├── chat.py              # Chat adapter (invoke + invoke_stream)
│   ├── token_count.py       # Token counting & normalization
│   ├── audio.py             # Audio adapter (optional)
│   └── image.py             # Image adapter (optional)
│
├── core/                    # Orchestration layer
│   ├── registry.py          # Auto-discovers and loads provider modules
│   ├── router.py            # Resolves model names to provider+model
│   ├── auth.py              # Bearer token auth + model whitelist
│   ├── call_log.py          # Unified request logging (JSONL)
│   └── usage.py             # Token usage & quota management
│
├── api/                     # FastAPI service layer
├── add_diy/                 # Scaffolding toolkit
├── web/                     # Web dashboard frontend
│
├── server.py                # Entry point
├── setup.py                 # Initialization wizard
├── agent_control.md         # AI agent operation guide
├── docker-compose.yml       # Docker deployment
└── Dockerfile               # Image build
```

### Core Conventions

| Convention | Description |
|------------|-------------|
| Model naming | `{provider}-{vendor_model}`, e.g. `deepseek-deepseek-v4-flash` |
| Provider isolation | Each provider directory is completely isolated — no cross-imports |
| Request/response format | Always OpenAI-compatible |
| Key source | Providers read API keys from environment variables |

## Related Projects

- [VOTX Agent](https://github.com/kesepain-KE/votx-agent) — Multi-user AI Agent framework. This project's `agent_control.md` is designed for such systems.

## Maintainers

- [@kesepain-KE](https://github.com/kesepain-KE)

## Contributing

PRs and Issues are welcome. The `agent_control.md` manual is designed to guide AI agents through provider development and configuration management, lowering the barrier for contribution.

### Contributors

Thanks to everyone who has contributed to this project.

## License

[MIT](LICENSE) © 2025 Kemo LLM Adapter Contributors
