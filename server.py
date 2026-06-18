#!/usr/bin/env python3
"""
Kemo LLM Adapter — API Server.

启动::

    python server.py
    python server.py --port 8000 --host 0.0.0.0

暴露两类接口：:

    /v1/chat/completions   — OpenAI-compatible chat endpoint
    /api/*                 — 管理面板 API
    /                      — Web 管理面板 (index.html)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import uvicorn

# 确保项目根在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import bootstrap, AppContext
from core.auth import (
    AuthError, KeyNotFoundError, KeyDisabledError, ModelNotAllowedError,
)
from core.usage import QuotaExceededError
from core.router import RouterError

# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("server")

# ---------------------------------------------------------------------------
# bootstrap core
# ---------------------------------------------------------------------------
ctx: AppContext = bootstrap(str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Kemo LLM Adapter",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Static — Web panel
# ---------------------------------------------------------------------------
_WEB_HTML = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def web_panel():
    return _WEB_HTML


# =========================================================================
# /v1/chat/completions — OpenAI-compatible
# =========================================================================

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat endpoint — 完整调用链路。"""
    # --- 提取 token ---
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        raise HTTPException(401, detail="missing Bearer token")

    body: dict[str, Any] = await request.json()
    stream: bool = body.get("stream", False)
    exposed_model: str = body.get("model", "")

    # --- 鉴权 ---
    t0 = time.perf_counter()
    try:
        key_info = ctx.auth.authenticate(token, exposed_model)
    except KeyNotFoundError:
        raise HTTPException(401, detail="invalid API key")
    except KeyDisabledError:
        raise HTTPException(403, detail="API key disabled")
    except ModelNotAllowedError:
        raise HTTPException(403, detail="model not allowed for this key")

    # --- 路由 ---
    try:
        route = ctx.router.resolve(exposed_model)
    except RouterError as exc:
        raise HTTPException(400, detail=str(exc))

    provider: str = route["provider"]
    vendor_model: str = route["model"]
    capability: str = route.get("capability", "chat")

    # 注入 vendor_model + extra
    body["model"] = vendor_model
    extra = route.get("extra", {})
    if extra:
        for k, v in extra.items():
            if k not in body:
                body[k] = v

    # --- 额度预检 ---
    try:
        ctx.usage.check_quota(token)
    except QuotaExceededError as exc:
        raise HTTPException(429, detail=str(exc))

    # --- 获取适配器 ---
    try:
        if capability == "chat":
            chat = ctx.registry.get_chat(provider)
        else:
            raise HTTPException(400, detail=f"capability '{capability}' not supported yet")
    except ModuleNotFoundError as exc:
        raise HTTPException(503, detail=str(exc))

    # --- 调用 ---
    try:
        if stream:
            async def sse_stream():
                first = True
                try:
                    async for chunk in chat.invoke_stream(body):
                        data = json.dumps(chunk, ensure_ascii=False)
                        if first:
                            yield f"data: {data}\n\n"
                            first = False
                        else:
                            yield f"data: {data}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as exc:
                    err = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    yield f"data: {err}\n\n"
                    yield "data: [DONE]\n\n"

            return StreamingResponse(sse_stream(), media_type="text/event-stream")

        response: dict[str, Any] = await chat.invoke(body)
        latency_ms = (time.perf_counter() - t0) * 1000

    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        # 记录错误日志
        ctx.call_log.log(
            key_id=token,
            key_name=key_info.get("name", token[:12]),
            provider=provider,
            model=vendor_model,
            capability=capability,
            request=body,
            response={},
            error=f"{type(exc).__name__}: {exc}",
            latency_ms=latency_ms,
        )
        raise HTTPException(502, detail=str(exc))

    # --- usage 归一化 ---
    usage = ctx.usage.count(provider, response, request=body)

    # --- 日志 + 额度扣减 ---
    ctx.call_log.log(
        key_id=token,
        key_name=key_info.get("name", token[:12]),
        provider=provider,
        model=vendor_model,
        capability=capability,
        request=body,
        response=response,
        usage=usage,
        latency_ms=latency_ms,
    )

    return JSONResponse(content=response)


# =========================================================================
# /api/health
# =========================================================================

@app.get("/api/health")
async def api_health():
    providers = ctx.registry.list_providers()
    online = sum(1 for p in providers if ctx.registry.has_capability(p, "chat"))
    models = ctx.router.list_visible()

    # Error rate from today
    today_summary = ctx.call_log.summary()
    total_req = today_summary.get("request_count", 0)
    err_count = today_summary.get("error_count", 0)
    error_rate = (err_count / total_req * 100) if total_req > 0 else 0.0

    return {
        "health_score": _health_score(online, len(providers), error_rate),
        "providers_online": online,
        "providers_total": len(providers),
        "models_exposed": len(ctx.router.list_all()),
        "models_visible": len(models),
        "error_rate_pct": round(error_rate, 2),
        "server_version": "0.1.0",
        "quota_enabled": True,
    }


def _health_score(online: int, total: int, error_rate: float) -> int:
    score = 100
    if total > 0:
        score -= max(0, (total - online) * 30)
    score -= min(error_rate * 10, 30)
    return max(0, int(score))


# =========================================================================
# /api/stats
# =========================================================================

@app.get("/api/stats")
async def api_stats(period: str = Query("today")):
    # 确定日期范围
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if period == "today":
        s_today = ctx.call_log.summary(date=today)
        s_yesterday = ctx.call_log.summary(date=_days_ago(today, 1))
        trend = _build_trend(7)
        recent = _recent_calls(5)
        return {
            "period": "today",
            "request_count": s_today["request_count"],
            "request_delta_pct": _delta_pct(s_today["request_count"], s_yesterday["request_count"]),
            "token_total": s_today["total_tokens"],
            "token_delta_pct": _delta_pct(s_today["total_tokens"], s_yesterday["total_tokens"]),
            "avg_latency_ms": s_today["avg_latency_ms"],
            "latency_delta_ms": round(s_today["avg_latency_ms"] - s_yesterday["avg_latency_ms"], 1),
            "error_rate_pct": round(
                s_today["error_count"] / max(s_today["request_count"], 1) * 100, 2
            ),
            "error_open_count": s_today["error_count"],
            "trend": trend,
            "recent_calls": recent,
            "by_provider": _by_provider_breakdown(date=today),
        }
    elif period in ("7d", "30d"):
        days = 7 if period == "7d" else 30
        trend = _build_trend(days)
        recent = _recent_calls(5)
        total_all = {"request_count": 0, "error_count": 0, "total_tokens": 0, "avg_latency_ms": 0.0}
        for i in range(days):
            s = ctx.call_log.summary(date=_days_ago(today, i))
            total_all["request_count"] += s["request_count"]
            total_all["error_count"] += s["error_count"]
            total_all["total_tokens"] += s["total_tokens"]
        total_all["avg_latency_ms"] = trend[-1]["requests"] if trend else 0
        return {
            "period": period,
            "request_count": total_all["request_count"],
            "request_delta_pct": 0,
            "token_total": total_all["total_tokens"],
            "token_delta_pct": 0,
            "avg_latency_ms": 0,
            "latency_delta_ms": 0,
            "error_rate_pct": round(
                total_all["error_count"] / max(total_all["request_count"], 1) * 100, 2
            ),
            "error_open_count": total_all["error_count"],
            "trend": trend,
            "recent_calls": recent,
            "by_provider": _by_provider_breakdown(),
        }
    else:
        raise HTTPException(400, detail=f"unknown period: {period}")


# =========================================================================
# /api/providers
# =========================================================================

@app.get("/api/providers")
async def api_providers():
    global_config = _load_json("config/config.json")
    result = []
    for name in ctx.registry.list_providers():
        cfg = ctx.registry.get_provider_config(name)
        g_enabled = global_config.get("providers", {}).get(name, {}).get("enabled", True)
        p_enabled = cfg.get("enabled", True)
        caps = list(ctx.registry._capabilities.get(name, {}).keys())
        result.append({
            "name": name,
            "enabled": g_enabled and p_enabled,
            "base_url": cfg.get("base_url", ""),
            "modules": list(cfg.get("modules", {}).keys()),
            "capabilities": caps,
            "models": list(cfg.get("models", {}).keys()),
        })
    # Also add providers that are in config but not loaded (disabled)
    for name, p_cfg in global_config.get("providers", {}).items():
        if name not in {r["name"] for r in result}:
            # Try to read model.json
            model_json = _load_json(f"provider/{name}/model.json")
            result.append({
                "name": name,
                "enabled": False,
                "base_url": model_json.get("base_url", ""),
                "modules": list(model_json.get("modules", {}).keys()),
                "capabilities": [],
                "models": list(model_json.get("models", {}).keys()),
            })
    return {"providers": result}


@app.post("/api/providers/{name}/toggle")
async def api_providers_toggle(name: str, req: Request):
    body = await req.json()
    enabled = body.get("enabled", True)
    cfg = _load_json("config/config.json")
    cfg.setdefault("providers", {})[name] = {"enabled": enabled}
    _save_json("config/config.json", cfg)
    return {"name": name, "enabled": enabled}


# =========================================================================
# /api/models
# =========================================================================

@app.get("/api/models")
async def api_models():
    models = ctx.router.list_all()
    return {"models": models}


@app.post("/api/models/{model_id}/toggle")
async def api_models_toggle(model_id: str, req: Request):
    body = await req.json()
    enabled = body.get("enabled", True)
    data = _load_json("config/models.json")
    if model_id not in data:
        raise HTTPException(404, detail=f"unknown model: {model_id}")
    data[model_id]["enabled"] = enabled
    _save_json("config/models.json", data)
    ctx.router.load()  # 重新加载
    return {"id": model_id, "enabled": enabled}


@app.post("/api/models/{model_id}/test")
async def api_models_test(model_id: str):
    """连通测试 — 发一个最小 chat 请求。"""
    try:
        route = ctx.router.resolve(model_id)
    except RouterError as exc:
        return {"ok": False, "error": str(exc)}

    provider = route["provider"]
    vendor_model = route["model"]

    # 找该 provider 任意一个密钥
    key_id, key_info = _first_key_for_model(model_id)
    if not key_id:
        return {"ok": False, "error": "no API key with access to this model"}

    try:
        chat = ctx.registry.get_chat(provider)
    except ModuleNotFoundError:
        return {"ok": False, "error": f"provider '{provider}' chat not loaded"}

    body = {
        "model": vendor_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 16,
    }
    extra = route.get("extra", {})
    for k, v in extra.items():
        if k not in body:
            body[k] = v

    t0 = time.perf_counter()
    try:
        resp = await chat.invoke(body)
        latency = (time.perf_counter() - t0) * 1000
        content = (resp.get("choices", [{}])[0].get("message", {}).get("content", "") or
                   str(resp.get("choices", [{}])[0])[:200])
        return {"ok": True, "latency_ms": round(latency, 1), "content": content[:200]}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# =========================================================================
# /api/keys
# =========================================================================

@app.get("/api/keys")
async def api_keys():
    keys = _load_json("config/api_keys.json").get("keys", {})
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


@app.post("/api/keys/{key_id}/models")
async def api_keys_models(key_id: str, req: Request):
    body = await req.json()
    models_list = body.get("models", [])
    data = _load_json("config/api_keys.json")
    if key_id not in data.get("keys", {}):
        raise HTTPException(404, detail=f"unknown key: {key_id}")
    data["keys"][key_id]["models"] = models_list
    _save_json("config/api_keys.json", data)
    ctx.auth.load()  # reload
    return {"id": key_id, "models": models_list}


# =========================================================================
# /api/logs
# =========================================================================

@app.get("/api/logs")
async def api_logs(
    status: str = Query("all"),
    q: str = Query(""),
    date: str = Query(""),
    limit: int = Query(50),
):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d = date if date else today

    # 读取所有 key 的日志
    all_entries: list[dict[str, Any]] = []
    call_log_dir = PROJECT_ROOT / "data_status" / "call_log"
    if call_log_dir.is_dir():
        for key_dir in call_log_dir.iterdir():
            if key_dir.is_dir():
                all_entries.extend(_read_jsonl(key_dir / f"{d}.jsonl"))

    # 按时间倒序
    all_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    # 过滤 status
    if status == "ok":
        all_entries = [e for e in all_entries if not e.get("error")]
    elif status == "error":
        all_entries = [e for e in all_entries if e.get("error")]

    # 过滤搜索
    if q:
        ql = q.lower()
        all_entries = [
            e for e in all_entries
            if ql in (e.get("key_id", "") or "").lower()
            or ql in (e.get("model", "") or "").lower()
            or ql in (e.get("provider", "") or "").lower()
        ]

    # 分页
    page = all_entries[:limit]

    # 汇总
    total_req = len(all_entries)
    err_count = sum(1 for e in all_entries if e.get("error"))

    summary = {
        "request_count": total_req,
        "error_count": err_count,
        "total_tokens": sum(e.get("usage", {}).get("total_tokens", 0) for e in all_entries),
        "prompt_tokens": sum(e.get("usage", {}).get("prompt_tokens", 0) for e in all_entries),
        "completion_tokens": sum(e.get("usage", {}).get("completion_tokens", 0) for e in all_entries),
        "avg_latency_ms": round(
            sum(e.get("latency_ms", 0) for e in all_entries) / max(total_req, 1), 2
        ),
    }

    return {"entries": page, "summary": summary}


# =========================================================================
# /api/usage
# =========================================================================

@app.get("/api/usage")
async def api_usage(
    period: str = Query("today"),
):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    days = {"today": 1, "7d": 7, "30d": 30, "month": 30}.get(period, 1)

    # 汇总
    all_entries: list[dict[str, Any]] = []
    call_log_dir = PROJECT_ROOT / "data_status" / "call_log"
    for i in range(days):
        d = _days_ago(today, i)
        if call_log_dir.is_dir():
            for key_dir in call_log_dir.iterdir():
                if key_dir.is_dir():
                    all_entries.extend(_read_jsonl(key_dir / f"{d}.jsonl"))

    total_req = len(all_entries)
    err_count = sum(1 for e in all_entries if e.get("error"))
    success_rate = (total_req - err_count) / max(total_req, 1) * 100

    # 延迟百分位
    latencies = sorted([e.get("latency_ms", 0) for e in all_entries if e.get("latency_ms", 0) > 0])
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)

    # 活跃密钥
    active_keys = len({e.get("key_id") for e in all_entries})

    # Provider 分解
    by_provider = _by_provider_breakdown(entries=all_entries)

    # 总计
    total_tokens = sum(e.get("usage", {}).get("total_tokens", 0) for e in all_entries)
    cache_hit = sum(e.get("usage", {}).get("prompt_cache_hit_tokens", 0) for e in all_entries)
    reasoning = sum(e.get("usage", {}).get("reasoning_tokens", 0) for e in all_entries)

    return {
        "period": period,
        "total_tokens": total_tokens,
        "request_count": total_req,
        "success_rate_pct": round(success_rate, 2),
        "active_keys": active_keys,
        "latency": {"p50_ms": p50, "p95_ms": p95, "p99_ms": p99},
        "cache": {
            "hit_tokens": cache_hit,
            "hit_pct": round(cache_hit / max(total_tokens, 1) * 100, 1),
        },
        "reasoning_tokens": reasoning,
        "by_provider": by_provider,
    }


# =========================================================================
# /api/config
# =========================================================================

@app.get("/api/config")
async def api_config():
    return {
        "config_json": _load_json("config/config.json"),
        "models_json": _load_json("config/models.json"),
        "api_keys_json": _load_json("config/api_keys.json"),
        "global_prompt": _read_text("config/global_prompt.md"),
        "provider_env": _read_text("provider.env"),
    }


@app.post("/api/config/{file}")
async def api_config_save(file: str, req: Request):
    body = await req.json()
    file_map = {
        "config": "config/config.json",
        "models": "config/models.json",
        "api_keys": "config/api_keys.json",
        "provider_env": "provider.env",
    }

    if file not in file_map:
        raise HTTPException(400, detail=f"unknown config file: {file}")

    path = file_map[file]

    if file == "global_prompt":
        _write_text("config/global_prompt.md", body.get("content", ""))
    elif file == "provider_env":
        _write_text("provider.env", body.get("content", ""))
    else:
        _save_json(path, body.get("content", body))

    # 重新加载 core
    if file == "config":
        ctx.registry.load_all()
    elif file == "models":
        ctx.router.load()
    elif file == "api_keys":
        ctx.auth.load()

    return {"saved": file}


# =========================================================================
# Helpers
# =========================================================================

def _load_json(rel_path: str) -> dict[str, Any]:
    try:
        return json.loads((PROJECT_ROOT / rel_path).read_text("utf-8"))
    except Exception:
        return {}


def _save_json(rel_path: str, data: dict[str, Any]) -> None:
    p = PROJECT_ROOT / rel_path
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _read_text(rel_path: str) -> str:
    try:
        return (PROJECT_ROOT / rel_path).read_text("utf-8")
    except Exception:
        return ""


def _write_text(rel_path: str, content: str) -> None:
    (PROJECT_ROOT / rel_path).write_text(content, encoding="utf-8")


def _read_jsonl(file_path: Path) -> list[dict[str, Any]]:
    if not file_path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in file_path.read_text("utf-8").strip().split("\n"):
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _days_ago(date_str: str, n: int) -> str:
    from datetime import timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return (d - timedelta(days=n)).strftime("%Y-%m-%d")


def _delta_pct(current: int, previous: int) -> float:
    if previous > 0:
        return round((current - previous) / previous * 100, 1)
    return 0.0


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = int(len(sorted_vals) * pct / 100)
    return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 1)


def _build_trend(days: int) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    trend: list[dict[str, Any]] = []
    for i in range(days - 1, -1, -1):
        d = _days_ago(today, i)
        s = ctx.call_log.summary(date=d)
        trend.append({
            "date": d,
            "requests": s["request_count"],
            "cache_hit": s["prompt_cache_hit_tokens"],
        })
    return trend


def _recent_calls(n: int) -> list[dict[str, Any]]:
    call_log_dir = PROJECT_ROOT / "data_status" / "call_log"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_entries: list[dict[str, Any]] = []
    if call_log_dir.is_dir():
        for key_dir in call_log_dir.iterdir():
            if key_dir.is_dir():
                all_entries.extend(_read_jsonl(key_dir / f"{today}.jsonl"))
    all_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return [
        {
            "request_id": e.get("request_id", ""),
            "model": e.get("model", ""),
            "latency_ms": e.get("latency_ms", 0),
            "total_tokens": e.get("usage", {}).get("total_tokens", 0),
            "error": e.get("error"),
        }
        for e in all_entries[:n]
    ]


def _by_provider_breakdown(
    date: str | None = None,
    entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if entries is None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_entries: list[dict[str, Any]] = []
        call_log_dir = PROJECT_ROOT / "data_status" / "call_log"
        d = date if date else today
        if call_log_dir.is_dir():
            for key_dir in call_log_dir.iterdir():
                if key_dir.is_dir():
                    all_entries.extend(_read_jsonl(key_dir / f"{d}.jsonl"))
    else:
        all_entries = entries

    by_p: dict[str, dict[str, Any]] = {}
    for e in all_entries:
        p = e.get("provider", "unknown")
        if p not in by_p:
            by_p[p] = {
                "provider": p,
                "request_count": 0,
                "error_count": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cache_hit_tokens": 0,
                "reasoning_tokens": 0,
                "total_latency_ms": 0.0,
                "latency_count": 0,
                "stream_count": 0,
                "tool_call_count": 0,
                "thinking_count": 0,
                "models": {},
            }
        bp = by_p[p]
        bp["request_count"] += 1
        if e.get("error"):
            bp["error_count"] += 1
        u = e.get("usage", {})
        bp["total_tokens"] += u.get("total_tokens", 0)
        bp["prompt_tokens"] += u.get("prompt_tokens", 0)
        bp["completion_tokens"] += u.get("completion_tokens", 0)
        bp["cache_hit_tokens"] += u.get("prompt_cache_hit_tokens", 0)
        bp["reasoning_tokens"] += u.get("reasoning_tokens", 0)
        lat = e.get("latency_ms", 0)
        if lat > 0:
            bp["total_latency_ms"] += lat
            bp["latency_count"] += 1
        if e.get("stream"):
            bp["stream_count"] += 1
        # 用 messages_summary 推断 tool_call / thinking
        msgs = e.get("messages_summary", [])
        if any("tool" in m.lower() for m in msgs):
            bp["tool_call_count"] += 1
        extra = e.get("capability", "")
        if extra == "chat" and "thinking" in str(e.get("usage", {})):
            bp["thinking_count"] += 1

        # per-model
        m = e.get("model", "unknown")
        if m not in bp["models"]:
            bp["models"][m] = {"model": m, "total_tokens": 0}
        bp["models"][m]["total_tokens"] += u.get("total_tokens", 0)

    result: list[dict[str, Any]] = []
    for bp in by_p.values():
        total = bp["total_tokens"] or 1
        reqs = bp["request_count"] or 1
        models_list = list(bp["models"].values())
        for m in models_list:
            m["pct"] = round(m["total_tokens"] / total * 100, 1)
        result.append({
            "provider": bp["provider"],
            "request_count": bp["request_count"],
            "total_tokens": bp["total_tokens"],
            "prompt_tokens": bp["prompt_tokens"],
            "completion_tokens": bp["completion_tokens"],
            "cache_hit_pct": round(bp["cache_hit_tokens"] / total * 100, 1),
            "reasoning_tokens": bp["reasoning_tokens"],
            "avg_latency_ms": round(bp["total_latency_ms"] / max(bp["latency_count"], 1), 1),
            "error_rate_pct": round(bp["error_count"] / reqs * 100, 2),
            "stream_pct": round(bp["stream_count"] / reqs * 100, 1),
            "tool_call_pct": round(bp["tool_call_count"] / reqs * 100, 1),
            "thinking_pct": round(bp["thinking_count"] / reqs * 100, 1),
            "models": models_list,
        })
    return result


def _first_key_for_model(model_id: str) -> tuple[str | None, dict[str, Any] | None]:
    keys = _load_json("config/api_keys.json").get("keys", {})
    for token, info in keys.items():
        if info.get("enabled", True) and model_id in info.get("models", []):
            return token, info
    return None, None


# =========================================================================
# Main
# =========================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kemo LLM Adapter Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    log.info("starting on %s:%d", args.host, args.port)
    log.info("providers: %s", ctx.registry.list_providers())
    log.info("models: %d", len(ctx.router.list_all()))

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
