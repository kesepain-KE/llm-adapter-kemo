"""聊天调用服务 — 鉴权 → 路由 → 调 provider → usage → log。"""

from __future__ import annotations

import time
from typing import Any

from core.router import RouterError
from api.errors import auth_to_http


async def handle_chat(
    ctx,
    token: str,
    body: dict[str, Any],
    stream: bool = False,
) -> dict[str, Any] | Any:
    """处理一次完整的聊天请求，返回响应 dict 或 StreamingResponse 所需的 async generator。

    抛出 HTTPException 时由 FastAPI 自动处理。
    """
    t0 = time.perf_counter()

    # 1. 鉴权
    exposed_model: str = body.get("model", "")
    try:
        key_info = ctx.auth.authenticate(token, exposed_model)
    except Exception as exc:
        raise auth_to_http(exc) from exc

    # 2. 路由
    try:
        route = ctx.router.resolve(exposed_model)
    except RouterError as exc:
        from fastapi import HTTPException
        raise HTTPException(400, detail=str(exc)) from exc

    provider: str = route["provider"]
    vendor_model: str = route["model"]
    capability: str = route.get("capability", "chat")

    # 注入 vendor_model + extra
    body["model"] = vendor_model
    extra = route.get("extra", {})
    for k, v in extra.items():
        if k not in body:
            body[k] = v

    # 3. 额度预检
    try:
        ctx.usage.check_quota(token)
    except Exception as exc:
        raise auth_to_http(exc) from exc

    # 4. 获取适配器
    from fastapi import HTTPException
    try:
        chat = ctx.registry.get_chat(provider)
    except ModuleNotFoundError as exc:
        raise HTTPException(503, detail=f"provider '{provider}' chat not loaded: {exc}")

    # 5. 调用
    try:
        if stream:
            return _stream_generator(chat, body, ctx, token, key_info, provider,
                                     vendor_model, capability, t0)
        response: dict[str, Any] = await chat.invoke(body)
        latency_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        ctx.call_log.log(
            key_id=token, key_name=key_info.get("name", token[:12]),
            provider=provider, model=vendor_model, capability=capability,
            request=body, response={},
            error=f"{type(exc).__name__}: {exc}", latency_ms=latency_ms,
        )
        raise HTTPException(502, detail=str(exc)) from exc

    # 6. usage + log
    usage = ctx.usage.count(provider, response, request=body)
    ctx.call_log.log(
        key_id=token, key_name=key_info.get("name", token[:12]),
        provider=provider, model=vendor_model, capability=capability,
        request=body, response=response, usage=usage, latency_ms=latency_ms,
    )
    return response


async def _stream_generator(chat, body, ctx, token, key_info, provider,
                            vendor_model, capability, t0_start):
    """SSE 流式 generator。"""
    import json as _json
    first = True
    try:
        async for chunk in chat.invoke_stream(body):
            data = _json.dumps(chunk, ensure_ascii=False)
            if first:
                yield f"data: {data}\n\n"
                first = False
            else:
                yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0_start) * 1000
        ctx.call_log.log(
            key_id=token, key_name=key_info.get("name", token[:12]),
            provider=provider, model=vendor_model, capability=capability,
            request=body, response={},
            error=f"{type(exc).__name__}: {exc}", latency_ms=latency_ms,
        )
        err = _json.dumps({"error": str(exc)}, ensure_ascii=False)
        yield f"data: {err}\n\n"
        yield "data: [DONE]\n\n"
