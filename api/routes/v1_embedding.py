"""POST /v1/embeddings — RAG Embedding endpoint。"""

from __future__ import annotations

import time

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from api.deps import get_ctx
from api.errors import capability_error
from api.services.v1_logging import log_v1_error, log_v1_success
from core.router import RouterError


async def embeddings(request: Request):
    """POST /v1/embeddings — 文本嵌入。

    Body (JSON):
        {
            "model": "...",
            "input": "text to embed" | ["text1", "text2"],
            "encoding_format": "float" | "base64"
        }

    注意: 需要 provider 有 embedding adapter。
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
    if not any(cap == "embedding" for cap in capabilities):
        raise capability_error("/v1/embeddings", model_id, "embedding", ", ".join(capabilities))

    try:
        emb = ctx.registry.get_embedding(route["provider"])
    except ModuleNotFoundError:
        raise HTTPException(
            503,
            detail=f"embedding adapter not loaded for {route['provider']}. "
                   "This provider does not have an embedding module.",
        )

    vendor_model = route["model"]
    body["model"] = vendor_model

    started_at = time.perf_counter()
    try:
        result = await emb.invoke(body)
    except Exception as exc:
        log_v1_error(
            ctx,
            token=token,
            key_info=key_info,
            provider=route["provider"],
            model=vendor_model,
            capability="embedding",
            request=body,
            started_at=started_at,
            error=exc,
        )
        raise HTTPException(502, detail=str(exc))

    log_v1_success(
        ctx,
        token=token,
        key_info=key_info,
        provider=route["provider"],
        model=vendor_model,
        capability="embedding",
        request=body,
        response=result,
        started_at=started_at,
    )

    return JSONResponse(content=result)


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    raise HTTPException(401, detail="missing Bearer token")
