"""GET/POST /api/config — 配置读写。"""

from fastapi import Request, HTTPException

from api.deps import get_ctx
from api.services import load_json, save_json, read_text, write_text


async def api_config():
    return {
        "config_json": load_json("config/config.json"),
        "models_json": load_json("config/models.json"),
        "api_keys_json": load_json("config/api_keys.json"),
        "global_prompt": read_text("config/global_prompt.md"),
        "provider_env": read_text("provider.env"),
    }


async def api_config_save(file: str, req: Request):
    body = await req.json()
    ctx = get_ctx()

    file_map = {
        "config": "config/config.json",
        "models": "config/models.json",
        "api_keys": "config/api_keys.json",
        "global_prompt": "config/global_prompt.md",
        "provider_env": "provider.env",
    }
    if file not in file_map:
        raise HTTPException(400, detail=f"unknown config file: {file}")

    path = file_map[file]

    if file == "global_prompt":
        write_text(path, body.get("content", ""))
    elif file == "provider_env":
        write_text(path, body.get("content", ""))
    else:
        save_json(path, body.get("content", body))

    # 重新加载相关模块
    if file == "config":
        get_ctx().registry.load_all()
    elif file == "models":
        ctx.router.load()
    elif file == "api_keys":
        ctx.auth.load()

    return {"saved": file}
