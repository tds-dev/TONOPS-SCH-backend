"""FastAPI アプリケーション: `uvicorn app.main:app --reload`。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  （全テーブルを登録）
from app.core.config import get_settings
from app.routers import jobs, masters, plans

API_PREFIX = "/api/v1"

app = FastAPI(
    title="Scheduler Platform API",
    version="0.1.0",
    description="Domain-neutral production / project scheduler (v0.1).",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in [*masters.routers, *jobs.routers, plans.router]:
    app.include_router(r, prefix=API_PREFIX)


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}
