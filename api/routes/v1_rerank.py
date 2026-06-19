"""POST /v1/rerank — RAG Rerank endpoint。"""

from __future__ import annotations

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from api.deps import get_ctx
from api.errors import capability_error
from core.router import RouterError


async def rerank(request: Request):
    """POST /v1/rerank — 文档重排。

    Body (JSON):
        {
            "model": "...",
            "query": "search query",
            "documents": ["doc1", "doc2", ...],
            "top_n": 3,
            "return_documents": true
        }

    注意: 需要 provider 有 rerank adapter。
    """
    token = _extract_token(request)
    body: dict = await request.json()
    model_id: str = body.get("model", "")

    ctx = get_ctx()

    try:
        key_info = ctx.auth.authenticate(token, model_id)
        route = ctx.router.resolve(model_id)
    except RouterError as exc:
        raise HTTPException(400, detail=str(exc))
    except Exception as exc:
        from api.errors import auth_to_http
        raise auth_to_http(exc) from exc

    capabilities = route["capabilities"]
    if not any(cap == "rerank" for cap in capabilities):
        raise capability_error("/v1/rerank", model_id, "rerank", ", ".join(capabilities))

    try:
        rerank_adapter = ctx.registry.get_rerank(route["provider"])
    except ModuleNotFoundError:
        raise HTTPException(
            503,
            detail=f"rerank adapter not loaded for {route['provider']}. "
                   "This provider does not have a rerank module.",
        )

    vendor_model = route["model"]
    body["model"] = vendor_model

    try:
        result = await rerank_adapter.invoke(body)
    except Exception as exc:
        raise HTTPException(502, detail=str(exc))

    return JSONResponse(content=result)


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    raise HTTPException(401, detail="missing Bearer token")
