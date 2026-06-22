"""POST /v1/audio/speech, POST /v1/audio/transcriptions — Audio endpoints。"""

from __future__ import annotations

import os
import tempfile
import time

from fastapi import Request, HTTPException, UploadFile, File, Form
from fastapi.responses import Response, JSONResponse

from api.deps import get_ctx
from api.errors import capability_error
from api.services.v1_logging import log_v1_error, log_v1_success
from core.router import RouterError


async def audio_speech(request: Request):
    """POST /v1/audio/speech — 文本转语音 (TTS)。

    Body (JSON):
        {
            "model": "stepfun-stepaudio-2.5-tts",
            "input": "你好世界",
            "voice": "cixingnansheng",
            "response_format": "mp3",
            "speed": 1.0
        }

    Response: audio bytes (Content-Type: audio/mpeg 等)。
    """
    token = _extract_token(request)
    body: dict = await request.json()
    model_id: str = body.get("model", "")

    ctx = get_ctx()

    # Auth + Route
    try:
        key_info = ctx.auth.authenticate(token, model_id)
        route = ctx.router.resolve(model_id)
    except RouterError as exc:
        raise HTTPException(400, detail=str(exc))
    except Exception as exc:
        from api.errors import auth_to_http
        raise auth_to_http(exc) from exc

    capabilities = route["capabilities"]
    if not any(cap.startswith("audio") and "tts" in cap for cap in capabilities):
        raise capability_error("/v1/audio/speech", model_id, "audio", ", ".join(capabilities))

    try:
        audio = ctx.registry.get_audio(route["provider"])
    except ModuleNotFoundError:
        raise HTTPException(503, detail=f"audio adapter not loaded for {route['provider']}")

    vendor_model = route["model"]
    body["model"] = vendor_model

    started_at = time.perf_counter()
    try:
        result = await audio.speech(body)
    except Exception as exc:
        log_v1_error(
            ctx,
            token=token,
            key_info=key_info,
            provider=route["provider"],
            model=vendor_model,
            capability="audio.tts",
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
        capability="audio.tts",
        request=body,
        response={},
        started_at=started_at,
    )

    # 推断 Content-Type
    fmt = body.get("response_format", "mp3")
    content_type = {
        "mp3": "audio/mpeg", "wav": "audio/wav",
        "flac": "audio/flac", "opus": "audio/opus", "pcm": "audio/pcm",
    }.get(fmt, "application/octet-stream")

    return Response(content=result, media_type=content_type)


async def audio_transcriptions(
    file: UploadFile = File(...),
    model: str = Form(...),
    language: str = Form("zh"),
    request: Request = None,
):
    """POST /v1/audio/transcriptions — 语音转文字 (ASR)。

    multipart/form-data:
        file: 音频文件
        model: 模型名 (如 "stepfun-stepaudio-2.5-asr")
        language: 语言 (默认 "zh")
    """
    token = _extract_token(request)
    model_id = model

    ctx = get_ctx()

    # Auth + Route
    try:
        key_info = ctx.auth.authenticate(token, model_id)
        route = ctx.router.resolve(model_id)
    except RouterError as exc:
        raise HTTPException(400, detail=str(exc))
    except Exception as exc:
        from api.errors import auth_to_http
        raise auth_to_http(exc) from exc

    capabilities = route["capabilities"]
    if not any(cap.startswith("audio") and "asr" in cap for cap in capabilities):
        raise capability_error("/v1/audio/transcriptions", model_id, "audio", ", ".join(capabilities))

    try:
        audio = ctx.registry.get_audio(route["provider"])
    except ModuleNotFoundError:
        raise HTTPException(503, detail=f"audio adapter not loaded for {route['provider']}")

    log_request = {
        "model": route["model"],
        "language": language,
        "file": file.filename or "",
    }

    # 保存上传文件到临时路径
    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    started_at = time.perf_counter()
    try:
        result = await audio.transcribe(
            audio_path=tmp_path,
            model=route["model"],
            language=language,
        )
    except Exception as exc:
        log_v1_error(
            ctx,
            token=token,
            key_info=key_info,
            provider=route["provider"],
            model=route["model"],
            capability="audio.asr",
            request=log_request,
            started_at=started_at,
            error=exc,
        )
        raise HTTPException(502, detail=str(exc))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    log_v1_success(
        ctx,
        token=token,
        key_info=key_info,
        provider=route["provider"],
        model=route["model"],
        capability="audio.asr",
        request=log_request,
        response=result,
        started_at=started_at,
    )

    return JSONResponse(content=result)


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    raise HTTPException(401, detail="missing Bearer token")
