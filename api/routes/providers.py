"""GET/POST /api/providers — Provider 注册表管理。"""

from fastapi import Request, HTTPException

from api.deps import get_ctx
from api.services import load_json, save_json


async def api_providers():
    ctx = get_ctx()
    global_config = load_json("config/config.json")
    result = []
    # 已加载的
    for name in ctx.registry.list_providers():
        cfg = ctx.registry.get_provider_config(name)
        g_enabled = global_config.get("providers", {}).get(name, {}).get("enabled", True)
        p_enabled = cfg.get("enabled", True)
        # 显示顶层能力（去重后的顶层 capability 名）
        all_caps = ctx.registry.list_capabilities(name)
        top_caps = sorted(set(c.split(".")[0] for c in all_caps))
        caps = top_caps
        result.append({
            "name": name,
            "enabled": g_enabled and p_enabled,
            "base_url": cfg.get("base_url", ""),
            "modules": list(cfg.get("modules", {}).keys()),
            "capabilities": caps,
            "models": list(cfg.get("models", {}).keys()),
        })
    # config 里声明但未加载的（禁用厂商）
    for name, p_cfg in global_config.get("providers", {}).items():
        if name not in {r["name"] for r in result}:
            model_json = load_json(f"provider/{name}/model.json")
            result.append({
                "name": name,
                "enabled": False,
                "base_url": model_json.get("base_url", ""),
                "modules": list(model_json.get("modules", {}).keys()),
                "capabilities": [],
                "models": list(model_json.get("models", {}).keys()),
            })
    return {"providers": result}


async def api_providers_toggle(name: str, req: Request):
    body = await req.json()
    enabled = body.get("enabled", True)
    cfg = load_json("config/config.json")
    cfg.setdefault("providers", {})[name] = {"enabled": enabled}
    save_json("config/config.json", cfg)
    return {"name": name, "enabled": enabled}
