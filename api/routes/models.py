"""GET/POST /api/models — 模型路由表管理。"""

from fastapi import Request, HTTPException

from api.deps import get_ctx
from api.services import load_json, save_json, probe_model


async def api_models():
    ctx = get_ctx()
    return {"models": ctx.router.list_all()}


async def api_models_toggle(model_id: str, req: Request):
    body = await req.json()
    enabled = body.get("enabled", True)
    data = load_json("config/models.json")
    if model_id not in data:
        raise HTTPException(404, detail=f"unknown model: {model_id}")
    data[model_id]["enabled"] = enabled
    save_json("config/models.json", data)
    get_ctx().router.load()
    return {"id": model_id, "enabled": enabled}


async def api_models_test(model_id: str):
    ctx = get_ctx()
    return await probe_model(ctx, model_id)
