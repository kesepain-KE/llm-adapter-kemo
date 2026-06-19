"""POST /v1/videos/generations, GET /v1/videos/{job_id}, GET /v1/videos/{job_id}/content。

Video endpoints — 异步任务框架预留。
当前 StepFun provider 无 video adapter，按 503 返回。
"""

from __future__ import annotations

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from api.deps import get_ctx
from api.errors import capability_error
from core.router import RouterError


async def video_generations(request: Request):
    """POST /v1/videos/generations — 创建视频生成任务。

    Body (JSON):
        {
            "model": "...",
            "prompt": "...",     # text_to_video
            "image": "...",      # image_to_video (base64 or URL)
            "video": "...",      # video_to_video (base64 or URL)
        }
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
    if not any(cap.startswith("video") for cap in capabilities):
        raise capability_error("/v1/videos/generations", model_id, "video", ", ".join(capabilities))

    try:
        video = ctx.registry.get_video(route["provider"])
    except ModuleNotFoundError:
        raise HTTPException(
            503,
            detail=f"video adapter not loaded for {route['provider']}. "
                   "Video endpoints require a video module which is not yet implemented.",
        )

    vendor_model = route["model"]
    body["model"] = vendor_model

    try:
        result = await video.create_job(body)
    except Exception as exc:
        raise HTTPException(502, detail=str(exc))

    return JSONResponse(content=result, status_code=202)


async def video_job_status(job_id: str, request: Request):
    """GET /v1/videos/{job_id} — 查询视频任务状态。"""
    token = _extract_token(request)
    ctx = get_ctx()

    # 视频任务状态查询不需要 model resolving
    # 从 job_id 前缀推断 provider
    provider = job_id.split("-")[0] if "-" in job_id else "stepfun"

    try:
        video = ctx.registry.get_video(provider)
    except ModuleNotFoundError:
        raise HTTPException(
            503, detail=f"video adapter not loaded for {provider}"
        )

    try:
        result = await video.get_job(job_id)
    except Exception as exc:
        raise HTTPException(502, detail=str(exc))

    return JSONResponse(content=result)


async def video_job_content(job_id: str, request: Request):
    """GET /v1/videos/{job_id}/content — 下载视频结果。"""
    token = _extract_token(request)
    ctx = get_ctx()

    provider = job_id.split("-")[0] if "-" in job_id else "stepfun"

    try:
        video = ctx.registry.get_video(provider)
    except ModuleNotFoundError:
        raise HTTPException(
            503, detail=f"video adapter not loaded for {provider}"
        )

    try:
        result = await video.get_content(job_id)
    except Exception as exc:
        raise HTTPException(502, detail=str(exc))

    return JSONResponse(content=result)


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    raise HTTPException(401, detail="missing Bearer token")
