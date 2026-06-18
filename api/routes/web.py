"""GET / — Web 管理面板。"""

from fastapi.responses import FileResponse, HTMLResponse

from api.deps import PROJECT_ROOT


async def web_panel():
    dist_index = PROJECT_ROOT / "web" / "dist" / "index.html"
    if dist_index.is_file():
        return FileResponse(dist_index)

    return HTMLResponse(
        content="""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kemo Adapter · Web build required</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: system-ui, sans-serif; background: #f6f8fb; color: #171717; }
    main { width: min(560px, calc(100% - 32px)); padding: 28px; border: 1px solid rgba(28,31,36,.12); border-radius: 10px; background: #fff; box-shadow: 0 18px 42px rgba(26,31,44,.10); }
    h1 { margin: 0 0 12px; font-size: 22px; }
    p { margin: 0 0 14px; color: #62666f; line-height: 1.6; }
    code { display: block; padding: 10px 12px; border-radius: 8px; background: #f1f5f9; color: #2a2c30; }
  </style>
</head>
<body>
  <main>
    <h1>React 管理面板尚未构建</h1>
    <p>请先生成 Vite 构建产物，然后刷新当前页面。</p>
    <code>cd web && npm install && npm run build</code>
  </main>
</body>
</html>""",
    )
