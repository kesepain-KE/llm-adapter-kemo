"""GET/POST /api/keys — API 密钥 + 模型白名单管理。"""

from fastapi import Request, HTTPException

from api.deps import get_ctx
from api.services import load_json, save_json


async def api_keys():
    keys = load_json("config/api_keys.json").get("keys", {})
    result = []
    for token, info in keys.items():
        result.append({
            "id": token,
            "name": info.get("name", ""),
            "enabled": info.get("enabled", True),
            "models": info.get("models", []),
            "quota": info.get("quota", {}),
        })
    return {"keys": result}


async def api_keys_models(key_id: str, req: Request):
    body = await req.json()
    models_list = body.get("models", [])
    data = load_json("config/api_keys.json")
    if key_id not in data.get("keys", {}):
        raise HTTPException(404, detail=f"unknown key: {key_id}")
    data["keys"][key_id]["models"] = models_list
    save_json("config/api_keys.json", data)
    get_ctx().auth.load()
    return {"id": key_id, "models": models_list}
