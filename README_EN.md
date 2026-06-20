# Kemo LLM Adapter

<p align="center">
  <img src="./llm-adapter-kemo.png" alt="Kemo LLM Adapter" width="300">
</p>

> Multi-provider LLM unified adapter — One API to access multiple LLM models

Kemo LLM Adapter is a lightweight API gateway that unifies multiple LLM providers (DeepSeek, StepFun, etc.) behind a single **OpenAI-compatible interface**. With one endpoint and one API key, you can switch between different models from different vendors.

---

## Table of Contents

- [Background](#background)
- [Installation](#installation)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Provider Development](#provider-development)
- [Architecture](#architecture)
- [Related Projects](#related-projects)
- [Maintainers](#maintainers)
- [License](#license)

---

## Background

As the LLM ecosystem grows, each provider offers its own API format, authentication method, and parameter conventions. Integrating multiple providers requires clients to maintain extensive adapter logic, making model switching expensive and error-prone.

Kemo LLM Adapter solves this by exposing all providers through a **unified OpenAI-compatible API**. Clients only need to talk to one endpoint and change the model name to switch between backends.

### Features

- **Unified API** — All providers share the OpenAI-compatible endpoint, supporting both streaming and non-streaming
- **Multi-modal** — TTS, ASR, image generation, image editing, video generation
- **Pluggable Providers** — Each provider lives in its own directory, auto-discovered by the registry. No framework code changes needed
- **API Key Management** — Per-key model whitelist + token quota control
- **Usage Analytics** — JSONL request logging, aggregated by key, provider, or model
- **Hot-Reload Config** — `config.json`, `models.json`, `api_keys.json` reload without restart
- **React Web Dashboard** — Vite + React dashboard for providers, models, and keys
- **Provider Scaffolding** — `add_diy.scaffold()` generates adapter boilerplate in one call
- **AI Agent Friendly** — `agent_control.md` guides AI agents to configure providers autonomously
- **Git-Based Updates** — automated with user config backup and restoration

## Installation

### Prerequisites

- Python >= 3.10
- pip
- Node.js >= 20 and npm (for Web dashboard)

### Get the Project

```bash
git clone https://github.com/kesepain-KE/llm-adapter-kemo.git
cd llm-adapter-kemo
```

### Initialize

```bash
python setup.py
```

Available flags:
- `--check` — check environment only
- `--install` — install dependencies only
- `--validate` — validate core modules only

`setup.py` runs Python version checks, detects dependencies (prompts to install if missing), creates required directories (`config/`, `data_status/call_log/`, `provider/`), and restores empty runtime config files when missing.

### Configuration

`python setup.py` creates empty runtime config on first run:

- `provider.env` copied from `provider.env.example`
- `config/config.json` copied from `config/config.json.example`
- `config/models.json` defaults to `{}`
- `config/api_keys.json` defaults to `{"keys": {}}`

Two approaches to configure provider API keys:

**Option A — Let an AI Agent handle it (recommended)**  
Have your AI assistant read `agent_control.md` and complete the provider setup automatically.

**Option B — Manual editing**
- `provider.env` — Fill in each provider's API keys
- `config/api_keys.json` — Set up internal keys and quotas
- `config/models.json` — Register models to expose

### Build the Web Dashboard

```bash
cd web && npm install && npm run build && cd ..
```

### Launch

```bash
python server.py
```

The server runs at `http://127.0.0.1:8741` by default.

### Update

```bash
python update.py            # interactive update
python update.py --check    # check version only
python update.py --yes      # non-interactive update
```

The update script automatically backs up `config/` and `provider.env`, pulls the latest code, then restores user configuration.

---

## Usage

### Model Registration (models.json)

```json
{
  "deepseek-deepseek-v4-flash": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "capabilities": ["chat"],
    "endpoint": "/v1/chat/completions",
    "enabled": true,
    "visible": true
  },
  "stepfun-stepaudio-2.5-tts": {
    "provider": "stepfun",
    "model": "stepaudio-2.5-tts",
    "capabilities": ["audio.tts"],
    "endpoint": "/v1/audio/speech",
    "enabled": true,
    "visible": true
  }
}
```

Model naming: `{provider}-{vendor_model}`, e.g. `deepseek-deepseek-v4-flash`.

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

## API Reference

### Base URL

```
http://<your-host>:8741
```

### Authentication

All requests require a Bearer token:

```bash
Authorization: Bearer sk-your-key
```

Keys are configured in `config/api_keys.json`, with per-key model whitelists and token quotas.

### Admin Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Service health check |
| `GET` | `/api/providers` | Provider list and status |
| `POST` | `/api/providers/{name}/toggle` | Enable/disable provider |
| `GET` | `/api/models` | Model list (including hidden) |
| `POST` | `/api/models/{id}/toggle` | Enable/disable model |
| `POST` | `/api/models/{id}/test` | Model connectivity test |
| `GET` | `/api/keys` | Key list |
| `POST` | `/api/keys/{id}/models` | Update key model whitelist |
| `GET` | `/api/logs` | Call logs |
| `GET` | `/api/stats` | Dashboard statistics |
| `GET` | `/api/usage` | Usage summary |
| `GET` | `/api/config` | View global prompt |
| `POST` | `/api/config/global_prompt` | Save global prompt |

### Model Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/models` | List visible models |
| `POST` | `/v1/chat/completions` | Chat completion (streaming + non-streaming) |
| `POST` | `/v1/audio/speech` | Text-to-speech |
| `POST` | `/v1/audio/transcriptions` | Speech-to-text |
| `POST` | `/v1/images/generations` | Image generation |
| `POST` | `/v1/images/edits` | Image editing |
| `POST` | `/v1/embeddings` | Text embeddings |
| `POST` | `/v1/rerank` | Rerank search results |
| `POST` | `/v1/videos/generations` | Video generation (async) |
| `GET` | `/v1/videos/{job_id}` | Video job status |
| `GET` | `/v1/videos/{job_id}/content` | Video job result |

### Supported Parameters — Chat Completions

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | — | Model ID (see `/v1/models`) |
| `messages` | array | — | OpenAI-format messages |
| `temperature` | number | 1.0 | Sampling temperature |
| `top_p` | number | 1.0 | Nucleus sampling |
| `max_tokens` | integer | 4096 | Max generated tokens |
| `stream` | boolean | false | Enable streaming |
| `stop` | string/array | null | Stop sequences |
| `tools` | array | null | Tool/function call definitions |
| `response_format` | object | null | e.g. `{"type": "json_object"}` |

## Provider Development

### Built-in Providers

| Provider | Module | Capabilities |
|----------|--------|--------------|
| **DeepSeek** | `provider/deepseek/` | chat · token_count |
| **StepFun** | `provider/stepfun/` | chat · token_count · audio (TTS/ASR) · image |

### Creating a New Provider

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
2. Edit `provider/minimax/token_count.py` (if needed)
3. Register models in `config/models.json`
4. Add API key in `provider.env`
5. Restart the server

For detailed guidance, refer to `agent_control.md`.

## Configuration

| File | Purpose | Hot-Reload |
|------|---------|------------|
| `provider.env` | Provider API keys (env vars) | ❌ Restart |
| `config/config.json` | Provider enable/disable | ✅ |
| `config/models.json` | Model name mapping | ✅ |
| `config/api_keys.json` | Client keys + whitelist + quota | ✅ |
| `config/global_prompt.md` | Global system prompt | ✅ |
| `provider/*/model.json` | Provider metadata | ❌ Restart |

See `.example` files under `config/` and `provider.env.example` for templates.

## Architecture

```
llm-adapter-kemo/
├── config/                  # Global configuration (hot-reload)
│   ├── config.json          # Provider enable/disable switches
│   ├── models.json          # Exposed model → provider+model mapping
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
│   ├── __init__.py          # bootstrap() + AppContext (DI container)
│   ├── registry.py          # Auto-discovers and loads provider modules
│   ├── router.py            # Resolves model names to provider+model
│   ├── auth.py              # Bearer token auth + model whitelist
│   ├── call_log.py          # Unified request logging (JSONL)
│   └── usage.py             # Token usage & quota management
│
├── api/                     # FastAPI service layer
│   ├── app.py               # Application entry point
│   ├── routes/              # API route handlers
│   ├── services/            # Business logic (auth, logging, stats)
│   └── utils/               # Utility functions
│
├── add_diy/                 # Provider scaffolding toolkit
├── web/                     # React/Vite Web admin panel
│   ├── src/                 # React source
│   ├── package.json         # Frontend dependencies
│   └── dist/                # Build output (generated locally)
│
├── server.py                # Entry point
├── setup.py                 # Initialization wizard
├── update.py                # Git-based update script (auto backup)
├── requirements.txt         # Python dependencies
├── version.json             # Version file
└── agent_control.md         # AI agent operation guide
```

### Core Conventions

| Convention | Description |
|------------|-------------|
| Model naming | `{provider}-{vendor_model}`, e.g. `deepseek-deepseek-v4-flash` |
| Provider isolation | Each provider directory is completely isolated — no cross-imports |
| Request/response format | Always OpenAI-compatible |
| Key source | Providers read API keys from environment variables |
| Factory-first loading | Modules created via `create_*` factory functions, falling back to direct class init |
| Config protection | `update.py` automatically backs up `config/` and `provider.env`, restores after pull |

## Related Projects

- [VOTX Agent](https://github.com/kesepain-KE/votx-agent) — Multi-user AI Agent framework. This project's `agent_control.md` is designed for such systems.

## Maintainers

- [@kesepain-KE](https://github.com/kesepain-KE)

## License

[MIT](LICENSE) © 2025 Kemo LLM Adapter Contributors
