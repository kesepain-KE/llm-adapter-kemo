"""FastAPI 应用工厂。"""

import mimetypes

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.deps import PROJECT_ROOT
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
    audio_speech, audio_transcriptions,
    image_generations, image_edits,
    embeddings,
    rerank,
    video_generations, video_job_status, video_job_content,
)

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")

app = FastAPI(
    title="Kemo LLM Adapter",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)

# ---- Web ----
web_dist = PROJECT_ROOT / "web" / "dist"
web_assets = web_dist / "assets"
if web_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=web_assets), name="web-assets")

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

# ---- /v1/audio ----
app.add_api_route("/v1/audio/speech", audio_speech, methods=["POST"])
app.add_api_route("/v1/audio/transcriptions", audio_transcriptions, methods=["POST"])

# ---- /v1/images ----
app.add_api_route("/v1/images/generations", image_generations, methods=["POST"])
app.add_api_route("/v1/images/edits", image_edits, methods=["POST"])

# ---- /v1/embeddings ----
app.add_api_route("/v1/embeddings", embeddings, methods=["POST"])

# ---- /v1/rerank ----
app.add_api_route("/v1/rerank", rerank, methods=["POST"])

# ---- /v1/videos ----
app.add_api_route("/v1/videos/generations", video_generations, methods=["POST"])
app.add_api_route("/v1/videos/{job_id}", video_job_status, methods=["GET"])
app.add_api_route("/v1/videos/{job_id}/content", video_job_content, methods=["GET"])


@app.api_route("/{path:path}", methods=["GET"])
async def serve_dist_static(path: str):
    """兜底：服务 web/dist 根目录下的剩余静态文件（如 logo.png）。"""
    file_path = web_dist / path
    if file_path.is_file():
        return FileResponse(file_path)
    return HTMLResponse(status_code=404, content="Not Found")
