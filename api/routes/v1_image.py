"""POST /v1/images/generations, POST /v1/images/edits — Image endpoints。"""

from __future__ import annotations

import os

from fastapi import Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from api.deps import get_ctx
from api.errors import capability_error
from core.router import RouterError


async def image_generations(request: Request):
    """POST /v1/images/generations — 文生图。

    Body (JSON):
        {
            "model": "...",
            "prompt": "...",
            "n": 1,
            "size": "1024x1024",
            "response_format": "url"
        }

    注意: 需要 provider 的 image adapter 支持 generate() 方法。
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
    if not any(cap.startswith("image") and "generation" in cap for cap in capabilities):
        raise capability_error("/v1/images/generations", model_id, "image", ", ".join(capabilities))

    try:
        image = ctx.registry.get_image(route["provider"])
    except ModuleNotFoundError:
        raise HTTPException(503, detail=f"image adapter not loaded for {route['provider']}")

    vendor_model = route["model"]
    body["model"] = vendor_model

    # 尝试 generate()，回退提示未实现
    if not hasattr(image, "generate"):
        raise HTTPException(
            503,
            detail="image generation not implemented for this provider",
        )

    try:
        result = await image.generate(body)
    except Exception as exc:
        raise HTTPException(502, detail=str(exc))

    return JSONResponse(content=result)


async def image_edits(
    image_file: UploadFile = File(...),
    prompt: str = Form(...),
    model: str = Form(...),
    response_format: str = Form("url"),
    request: Request = None,
):
    """POST /v1/images/edits — 图像编辑 (img2img)。

    multipart/form-data:
        image: 图片文件
        prompt: 编辑描述
        model: 模型名 (如 "stepfun-step-image-edit-2")
        response_format: "url" 或 "b64_json"
    """
    token = _extract_token(request)
    model_id = model

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
    if not any(cap.startswith("image") and "edit" in cap for cap in capabilities):
        raise capability_error("/v1/images/edits", model_id, "image", ", ".join(capabilities))

    try:
        image = ctx.registry.get_image(route["provider"])
    except ModuleNotFoundError:
        raise HTTPException(503, detail=f"image adapter not loaded for {route['provider']}")

    image_data = await image_file.read()
    image_filename = image_file.filename or "image.png"

    edit_request = {
        "model": route["model"],
        "image": image_data,
        "image_filename": image_filename,
        "prompt": prompt,
        "response_format": response_format,
    }

    try:
        result = await image.edit(edit_request)
    except Exception as exc:
        raise HTTPException(502, detail=str(exc))

    return JSONResponse(content=result)


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    raise HTTPException(401, detail="missing Bearer token")
