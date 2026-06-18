"""FastAPI 应用工厂。"""

from fastapi import FastAPI

from api.routes import (
    web_panel,
    api_health,
    api_stats,
    api_providers, api_providers_toggle,
    api_models, api_models_toggle, api_models_test,
    api_keys, api_keys_models,
    api_logs,
    api_usage,
    api_config, api_config_save,
    chat_completions,
)

app = FastAPI(
    title="Kemo LLM Adapter",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)

# ---- Web ----
app.add_api_route("/", web_panel, methods=["GET"], response_class=None)

# ---- /v1/chat/completions ----
app.add_api_route("/v1/chat/completions", chat_completions, methods=["POST"])

# ---- /api/health ----
app.add_api_route("/api/health", api_health, methods=["GET"])

# ---- /api/stats ----
app.add_api_route("/api/stats", api_stats, methods=["GET"])

# ---- /api/providers ----
app.add_api_route("/api/providers", api_providers, methods=["GET"])
app.add_api_route("/api/providers/{name}/toggle", api_providers_toggle, methods=["POST"])

# ---- /api/models ----
app.add_api_route("/api/models", api_models, methods=["GET"])
app.add_api_route("/api/models/{model_id}/toggle", api_models_toggle, methods=["POST"])
app.add_api_route("/api/models/{model_id}/test", api_models_test, methods=["POST"])

# ---- /api/keys ----
app.add_api_route("/api/keys", api_keys, methods=["GET"])
app.add_api_route("/api/keys/{key_id}/models", api_keys_models, methods=["POST"])

# ---- /api/logs ----
app.add_api_route("/api/logs", api_logs, methods=["GET"])

# ---- /api/usage ----
app.add_api_route("/api/usage", api_usage, methods=["GET"])

# ---- /api/config ----
app.add_api_route("/api/config", api_config, methods=["GET"])
app.add_api_route("/api/config/{file}", api_config_save, methods=["POST"])
