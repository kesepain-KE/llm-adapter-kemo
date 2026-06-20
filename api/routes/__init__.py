from .web import web_panel
from .health import api_health
from .stats import api_stats
from .providers import api_providers, api_providers_toggle
from .models import api_models, api_models_toggle, api_models_test
from .keys import api_keys, api_keys_models
from .logs import api_logs
from .usage import api_usage
from .v1_models import v1_list_models, v1_get_model
from .config import api_config, api_config_save
from .auth import api_auth_login, AuthMiddleware
from .v1 import chat_completions
from .v1_audio import audio_speech, audio_transcriptions
from .v1_image import image_generations, image_edits
from .v1_embedding import embeddings
from .v1_rerank import rerank
from .v1_video import video_generations, video_job_status, video_job_content

__all__ = [
    "web_panel",
    "api_health",
    "api_stats",
    "api_providers", "api_providers_toggle",
    "api_models", "api_models_toggle", "api_models_test",
    "api_keys", "api_keys_models",
    "api_logs",
    "api_usage",
    "api_config", "api_config_save",
    "api_auth_login", "AuthMiddleware",
    "chat_completions",
    "audio_speech", "audio_transcriptions",
    "image_generations", "image_edits",
    "embeddings",
    "rerank",
    "video_generations", "video_job_status", "video_job_content",
    "v1_list_models", "v1_get_model",
]
