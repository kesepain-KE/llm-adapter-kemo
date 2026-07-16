"""聊天调用服务 — 鉴权 → 路由 → 调 provider → usage → log。"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
import uuid
from typing import Any

import httpx

from core.call_log import exception_message
from core.concurrency import ConcurrencyLimitError
from core.router import RouterError
from api.errors import auth_to_http
from api.services.config_store import read_text


STREAM_HEARTBEAT_SECONDS = 15.0
logger = logging.getLogger(__name__)


def _non_negative_int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


CONNECT_RETRIES = _non_negative_int_env("KEMO_CONNECT_RETRIES", 2)
CONNECT_RETRY_BASE_SECONDS = 0.5
CONNECT_RETRY_MAX_SECONDS = 2.0


def _is_connect_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (httpx.ConnectError, httpx.ConnectTimeout)):
            return True
        current = current.__cause__ or current.__context__
    return False


def _connect_retry_delay(retry_number: int) -> float:
    base = min(
        CONNECT_RETRY_MAX_SECONDS,
        CONNECT_RETRY_BASE_SECONDS * (2 ** max(0, retry_number - 1)),
    )
    return base + random.uniform(0, base * 0.25)


async def _invoke_with_connect_retries(chat, body, provider, request_id, state):
    for attempt in range(1, CONNECT_RETRIES + 2):
        state["attempt_count"] = attempt
        try:
            return await chat.invoke(body)
        except Exception as exc:
            if not _is_connect_error(exc) or attempt > CONNECT_RETRIES:
                raise
            delay = _connect_retry_delay(attempt)
            logger.warning(
                "request_id=%s provider=%s connect retry=%d delay=%.2fs error=%s",
                request_id, provider, attempt, delay, exception_message(exc),
            )
            await asyncio.sleep(delay)


async def _stream_with_connect_retries(chat, body, provider, request_id, state):
    """Retry connection failures only before the first upstream chunk."""
    for attempt in range(1, CONNECT_RETRIES + 2):
        state["attempt_count"] = attempt
        emitted = False
        try:
            async for chunk in chat.invoke_stream(body):
                emitted = True
                state["upstream_emitted"] = True
                yield chunk
            return
        except Exception as exc:
            if emitted or not _is_connect_error(exc) or attempt > CONNECT_RETRIES:
                raise
            delay = _connect_retry_delay(attempt)
            logger.warning(
                "request_id=%s provider=%s stream connect retry=%d "
                "delay=%.2fs error=%s",
                request_id, provider, attempt, delay, exception_message(exc),
            )
            await asyncio.sleep(delay)


async def _iterate_with_heartbeat(stream):
    """Yield provider chunks while keeping the downstream SSE connection alive.

    A provider can legitimately take several minutes between data events.  The
    pending ``anext`` task must not be cancelled when a heartbeat is due,
    otherwise timing out one wait would also tear down the upstream stream.
    """
    iterator = stream.__aiter__()
    pending: asyncio.Task | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait(
                {pending}, timeout=STREAM_HEARTBEAT_SECONDS
            )
            if not done:
                yield True, None
                continue

            completed = pending
            pending = None
            try:
                chunk = completed.result()
            except StopAsyncIteration:
                return
            yield False, chunk
    finally:
        if pending is not None:
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass


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
    request_id = f"kemo-{uuid.uuid4().hex}"
    retry_state = {"attempt_count": 1, "upstream_emitted": False}

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

    # 5. 并发准入
    try:
        lease = await ctx.concurrency.acquire(provider)
    except ConcurrencyLimitError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        ctx.call_log.log(
            key_id=token, key_name=key_info.get("name", token[:12]),
            provider=provider, model=vendor_model, capability=capability,
            request=body, response={},
            error=f"{type(exc).__name__}: {exception_message(exc)}", exception=exc,
            error_phase="gateway_queue", request_id=request_id,
            attempt_count=1, latency_ms=latency_ms,
            completion_latency_ms=latency_ms,
        )
        raise HTTPException(
            429,
            detail={
                "error": {
                    "message": str(exc),
                    "type": "concurrency_limit",
                    "code": "gateway_busy",
                    "request_id": request_id,
                }
            },
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    # 6. 调用
    try:
        if stream:
            return _stream_generator(chat, body, ctx, token, key_info, provider,
                                     vendor_model, capability, t0, lease=lease,
                                     request_id=request_id, retry_state=retry_state)
        response: dict[str, Any] = await _invoke_with_connect_retries(
            chat, body, provider, request_id, retry_state
        )
        latency_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        ctx.call_log.log(
            key_id=token, key_name=key_info.get("name", token[:12]),
            provider=provider, model=vendor_model, capability=capability,
            request=body, response={},
            error=f"{type(exc).__name__}: {exception_message(exc)}", exception=exc,
            error_phase="upstream_connect" if _is_connect_error(exc) else "upstream_request",
            request_id=request_id, attempt_count=retry_state["attempt_count"],
            latency_ms=latency_ms,
            completion_latency_ms=latency_ms,
        )
        raise HTTPException(502, detail=exception_message(exc)) from exc
    finally:
        if not stream:
            await lease.release()

    # 7. usage + log
    usage = ctx.usage.count(provider, response, request=body)
    ctx.call_log.log(
        key_id=token, key_name=key_info.get("name", token[:12]),
        provider=provider, model=vendor_model, capability=capability,
        request=body, response=response, usage=usage, latency_ms=latency_ms,
        completion_latency_ms=latency_ms,
        request_id=request_id, attempt_count=retry_state["attempt_count"],
    )
    return response


async def _stream_generator(chat, body, ctx, token, key_info, provider,
                            vendor_model, capability, t0_start, lease=None,
                            request_id="", retry_state=None):
    """SSE 流式 generator。

    ``[DONE]`` 只表示上游完整结束。异常路径发送结构化 ``error`` 事件后
    直接关闭流，避免客户端把失败误判成成功结束。
    """
    import json as _json
    response_latency_ms = None
    final_usage = None
    retry_state = retry_state or {"attempt_count": 1, "upstream_emitted": False}
    response_stub: dict[str, Any] = {"id": "", "model": vendor_model, "choices": []}
    try:
        async for is_heartbeat, chunk in _iterate_with_heartbeat(
            _stream_with_connect_retries(
                chat, body, provider, request_id, retry_state
            )
        ):
            if is_heartbeat:
                # SSE comment: clients ignore it as content, while every hop
                # still observes bytes and resets its idle-read timeout.
                yield ": keep-alive\n\n"
                continue
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
            request_id=request_id, attempt_count=retry_state["attempt_count"],
        )
        yield "data: [DONE]\n\n"
    except asyncio.CancelledError as exc:
        completion_latency_ms = (time.perf_counter() - t0_start) * 1000
        if response_latency_ms is None:
            response_latency_ms = completion_latency_ms
        ctx.call_log.log(
            key_id=token, key_name=key_info.get("name", token[:12]),
            provider=provider, model=vendor_model, capability=capability,
            request=body, response=response_stub,
            error="CancelledError: downstream client disconnected", exception=exc,
            error_phase="downstream_disconnect", request_id=request_id,
            attempt_count=retry_state["attempt_count"],
            latency_ms=response_latency_ms,
            completion_latency_ms=completion_latency_ms,
        )
        raise
    except Exception as exc:
        completion_latency_ms = (time.perf_counter() - t0_start) * 1000
        if response_latency_ms is None:
            response_latency_ms = completion_latency_ms
        ctx.call_log.log(
            key_id=token, key_name=key_info.get("name", token[:12]),
            provider=provider, model=vendor_model, capability=capability,
            request=body, response=response_stub,
            error=f"{type(exc).__name__}: {exception_message(exc)}", exception=exc,
            error_phase=(
                "upstream_connect"
                if _is_connect_error(exc) and not retry_state["upstream_emitted"]
                else "upstream_stream"
            ),
            request_id=request_id, attempt_count=retry_state["attempt_count"],
            latency_ms=response_latency_ms,
            completion_latency_ms=completion_latency_ms,
        )
        error_payload = {
            "error": {
                "message": exception_message(exc),
                "type": "upstream_stream_error",
                "code": "stream_interrupted",
                "exception_type": type(exc).__name__,
                "request_id": request_id,
            }
        }
        err = _json.dumps(error_payload, ensure_ascii=False)
        yield f"data: {err}\n\n"
    finally:
        if lease is not None:
            await lease.release()
