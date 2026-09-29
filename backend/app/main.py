import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, engine, init_db
from .routers import router
from .synthetic import seed_if_empty

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    (_BACKEND_ROOT / "data").mkdir(exist_ok=True)
    init_db()
    if settings.seed_on_startup:
        db: Session = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(
    title="烘焙批次过程记录 RoastLog",
    version="1.0.0",
    description="豆温/环境温度/操作事件的过程记录与对比（不连接真实烘焙机）",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "database_url_scheme": settings.database_url.split(":", 1)[0],
        "ror_default_window_s": settings.default_ror_window_s,
        "max_interp_gap_s": settings.default_max_interp_gap_s,
    }


# 生产模式下托管已构建的前端（frontend/dist）
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_dist / "assets")),
        name="assets",
    )

    @app.get("/")
    def index():
        return FileResponse(str(_dist / "index.html"))

    @app.get("/compare")
    def compare_page():
        return FileResponse(str(_dist / "index.html"))
