"""聊天调用服务 — 鉴权 → 路由 → 调 provider → usage → log。"""

from __future__ import annotations

import time
from typing import Any

from core.router import RouterError
from api.errors import auth_to_http
from api.services.config_store import read_text


def _inject_global_system(body: dict) -> None:
    """自动注入 global_prompt.md 作为 system 消息（如果尚无 system 消息）。"""
    messages = body.get("messages")
    if not isinstance(messages, list):
        return
    global_prompt = read_text("config/global_prompt.md")
    if not global_prompt.strip():
        return
    if any(m.get("role") == "system" for m in messages):
        return
    messages.insert(0, {"role": "system", "content": global_prompt.strip()})


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
    capability: str = route.get("capability", "chat")  # 向后兼容

    # /v1/chat/completions 只接受 chat / vision.* 模型
    capabilities = route.get("capabilities", [capability])
    if not any(cap.split(".")[0] in ("chat", "vision") for cap in capabilities):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": (
                        f"model '{exposed_model}' capabilities {capabilities} "
                        f"does not support /v1/chat/completions"
                    ),
                    "type": "capability_mismatch",
                    "code": 400,
                }
            },
        )

    # 注入全局安全基座提示词（global_prompt.md）
    _inject_global_system(body)

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
            completion_latency_ms=latency_ms,
        )
        raise HTTPException(502, detail=str(exc)) from exc

    # 6. usage + log
    usage = ctx.usage.count(provider, response, request=body)
    ctx.call_log.log(
        key_id=token, key_name=key_info.get("name", token[:12]),
        provider=provider, model=vendor_model, capability=capability,
        request=body, response=response, usage=usage, latency_ms=latency_ms,
        completion_latency_ms=latency_ms,
    )
    return response


async def _stream_generator(chat, body, ctx, token, key_info, provider,
                            vendor_model, capability, t0_start):
    """SSE 流式 generator。"""
    import json as _json
    first = True
    response_latency_ms = None
    final_usage = None
    response_stub: dict[str, Any] = {"id": "", "model": vendor_model, "choices": []}
    try:
        async for chunk in chat.invoke_stream(body):
            if isinstance(chunk, dict):
                if response_latency_ms is None:
                    response_latency_ms = (time.perf_counter() - t0_start) * 1000
                if chunk.get("id"):
                    response_stub["id"] = chunk["id"]
                if chunk.get("model"):
                    response_stub["model"] = chunk["model"]
                if chunk.get("choices"):
                    response_stub["choices"] = chunk["choices"]
                if chunk.get("usage"):
                    final_usage = chunk["usage"]
            data = _json.dumps(chunk, ensure_ascii=False)
            if first:
                yield f"data: {data}\n\n"
                first = False
            else:
                yield f"data: {data}\n\n"

        completion_latency_ms = (time.perf_counter() - t0_start) * 1000
        if response_latency_ms is None:
            response_latency_ms = completion_latency_ms
        response_for_usage = {"usage": final_usage} if final_usage else {}
        usage = ctx.usage.count(provider, response_for_usage, request=body)
        ctx.call_log.log(
            key_id=token, key_name=key_info.get("name", token[:12]),
            provider=provider, model=vendor_model, capability=capability,
            request=body, response=response_stub, usage=usage,
            latency_ms=response_latency_ms,
            completion_latency_ms=completion_latency_ms,
        )
        yield "data: [DONE]\n\n"
    except Exception as exc:
        completion_latency_ms = (time.perf_counter() - t0_start) * 1000
        if response_latency_ms is None:
            response_latency_ms = completion_latency_ms
        ctx.call_log.log(
            key_id=token, key_name=key_info.get("name", token[:12]),
            provider=provider, model=vendor_model, capability=capability,
            request=body, response=response_stub,
            error=f"{type(exc).__name__}: {exc}",
            latency_ms=response_latency_ms,
            completion_latency_ms=completion_latency_ms,
        )
        err = _json.dumps({"error": str(exc)}, ensure_ascii=False)
        yield f"data: {err}\n\n"
        yield "data: [DONE]\n\n"
