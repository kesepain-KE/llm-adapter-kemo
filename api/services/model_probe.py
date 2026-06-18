"""模型连通测试。"""

from __future__ import annotations

import time

from api.services.config_store import load_json


def _first_key_for_model(model_id: str) -> tuple[str | None, dict | None]:
    """查找有权限访问指定模型的第一个密钥。"""
    keys = load_json("config/api_keys.json").get("keys", {})
    for token, info in keys.items():
        if info.get("enabled", True) and model_id in info.get("models", []):
            return token, info
    return None, None


async def probe_model(ctx, model_id: str) -> dict:
    """对指定模型发送一个最小 chat 请求。"""
    from core.router import RouterError

    try:
        route = ctx.router.resolve(model_id)
    except RouterError as exc:
        return {"ok": False, "error": str(exc)}

    provider = route["provider"]
    vendor_model = route["model"]

    key_id, key_info = _first_key_for_model(model_id)
    if not key_id:
        return {"ok": False, "error": "no API key with access to this model"}

    try:
        chat = ctx.registry.get_chat(provider)
    except ModuleNotFoundError:
        return {"ok": False, "error": f"provider '{provider}' chat not loaded"}

    body = {
        "model": vendor_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 16,
    }
    extra = route.get("extra", {})
    for k, v in extra.items():
        if k not in body:
            body[k] = v

    t0 = time.perf_counter()
    try:
        resp = await chat.invoke(body)
        latency = (time.perf_counter() - t0) * 1000
        content = (
            resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            or str(resp.get("choices", [{}])[0])[:200]
        )
        return {"ok": True, "latency_ms": round(latency, 1), "content": content[:200]}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
