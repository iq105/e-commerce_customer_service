import sys
from pathlib import Path

# 允许从任意目录运行（如 python backend/app/server/main_server.py），也能找到 backend 包
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.observability.prometheus_metrics import start_metrics_server
from backend.app.server.ws import router as ws_router

app = FastAPI(title="Ecom CS")

app.include_router(ws_router)

# 静态文件（前端）
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(static_dir / "index.html"))


@app.on_event("startup")
async def startup():
    start_metrics_server(port=8000)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)