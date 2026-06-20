"""GET /v1/models — OpenAI-compatible 模型列表端点。"""

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from api.deps import get_ctx


async def v1_list_models(request: Request):
    """GET /v1/models — 列出所有对外可见的模型。"""
    # 鉴权：验证 Bearer token 是否存在且启用
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, detail="missing Bearer token")
    token = auth_header[7:]

    ctx = get_ctx()
    key_info = ctx.auth.get_key(token)
    if key_info is None:
        raise HTTPException(401, detail="invalid API key")
    if not key_info.get("enabled", True):
        raise HTTPException(403, detail="API key is disabled")

    # 获取该密钥有权限使用的模型列表
    allowed_models = set(key_info.get("models", []))

    # 从 router 获取所有可见模型
    visible = ctx.router.list_visible()

    data = []
    for m in visible:
        model_id = m["id"]
        # 如果密钥配置了模型白名单，只返回白名单内的模型
        if allowed_models and model_id not in allowed_models:
            continue
        data.append({
            "id": model_id,
            "object": "model",
            "created": 0,
            "owned_by": m.get("provider", "unknown"),
        })

    return JSONResponse(content={
        "object": "list",
        "data": data,
    })


async def v1_get_model(request: Request, model_id: str):
    """GET /v1/models/{model_id} — 获取单个模型详情。"""
    # 鉴权
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, detail="missing Bearer token")
    token = auth_header[7:]

    ctx = get_ctx()
    key_info = ctx.auth.get_key(token)
    if key_info is None:
        raise HTTPException(401, detail="invalid API key")
    if not key_info.get("enabled", True):
        raise HTTPException(403, detail="API key is disabled")

    # 检查模型是否在密钥白名单中
    allowed_models = set(key_info.get("models", []))
    if allowed_models and model_id not in allowed_models:
        raise HTTPException(403, detail=f"model '{model_id}' not allowed for this key")

    # 从 router 查找模型
    try:
        route = ctx.router.resolve(model_id)
    except Exception:
        raise HTTPException(404, detail=f"model '{model_id}' not found")

    return JSONResponse(content={
        "id": model_id,
        "object": "model",
        "created": 0,
        "owned_by": route.get("provider", "unknown"),
        "capabilities": route.get("capabilities", []),
        "endpoint": route.get("endpoint", "/v1/chat/completions"),
    })
