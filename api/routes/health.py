"""GET /api/health — 系统健康快照。"""

from api.deps import get_ctx
from api.services.config_store import read_display_base_url


def _health_score(online: int, total: int, error_rate: float) -> int:
    score = 100
    if total > 0:
        score -= max(0, (total - online) * 30)
    score -= min(error_rate * 10, 30)
    return max(0, int(score))


async def api_health():
    ctx = get_ctx()
    providers = ctx.registry.list_providers()
    online = sum(1 for p in providers if ctx.registry.has_capability(p, "chat"))
    models = ctx.router.list_visible()

    today_summary = ctx.call_log.summary()
    total_req = today_summary.get("request_count", 0)
    err_count = today_summary.get("error_count", 0)
    error_rate = (err_count / total_req * 100) if total_req > 0 else 0.0

    return {
        "health_score": _health_score(online, len(providers), error_rate),
        "providers_online": online,
        "providers_total": len(providers),
        "models_exposed": len(ctx.router.list_all()),
        "models_visible": len(models),
        "error_rate_pct": round(error_rate, 2),
        "server_version": "0.1.0",
        "quota_enabled": True,
        "concurrency": ctx.concurrency.snapshot(),
        "base_url": read_display_base_url(),
    }
