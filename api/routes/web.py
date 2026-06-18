"""GET / — Web 管理面板。"""

from fastapi.responses import HTMLResponse

from api.deps import PROJECT_ROOT


async def web_panel():
    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)
