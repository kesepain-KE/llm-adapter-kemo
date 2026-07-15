"""POST /v1/chat/completions — OpenAI-compatible chat endpoint。"""

from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from api.deps import get_ctx
from api.services import handle_chat


async def chat_completions(request: Request):
    # 提取 token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        raise HTTPException(401, detail="missing Bearer token")

    body: dict = await request.json()
    stream: bool = body.get("stream", False)

    ctx = get_ctx()

    try:
        result = await handle_chat(ctx, token, body, stream)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, detail=str(exc)) from exc

    if stream:
        return StreamingResponse(
            result,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )
    return JSONResponse(content=result)
