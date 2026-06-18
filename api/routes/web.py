"""GET / — Web 管理面板。"""

from fastapi.responses import HTMLResponse

from api.deps import PROJECT_ROOT

_WEB_HTML = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")


async def web_panel():
    return HTMLResponse(content=_WEB_HTML)
