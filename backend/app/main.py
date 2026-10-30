"""API backend (FastAPI) – phần triển khai lên Render cho môn Điện toán đám mây.

Phụ trách: TV1.
Chạy trên máy:  uvicorn backend.app.main:app --reload        (từ thư mục gốc project)
Tài liệu API tự sinh:  http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from graphrag.common.config import load_config
from graphrag.resources import Resources

from .routers import admin, ask, documents, feedback, graph, system

log = logging.getLogger("graphrag")


def _warm_up(res: Resources) -> None:
    """Mở kết nối DB và dựng chỉ mục BM25 ngay khi khởi động để câu hỏi đầu tiên không bị chậm.
    Chạy nền: lỗi ở đây (vd. Docker chưa bật) chỉ ghi log, không chặn server."""
    try:
        _ = res.bm25
        res.neo4j.verify_connectivity()
        log.warning("Sẵn sàng: đã dựng chỉ mục BM25 và kết nối Neo4j")
    except Exception as e:  # noqa: BLE001
        log.warning("Chưa khởi động sẵn được (%s: %s). Kiểm tra Docker/.env", type(e).__name__, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()                 # APP_ENV=cloud trên Render
    app.state.res = Resources(cfg)      # chưa kết nối DB ở đây (lazy)
    if os.getenv("WARMUP", "1") == "1":
        threading.Thread(target=_warm_up, args=(app.state.res,), daemon=True).start()
    yield
    app.state.res.close()


app = FastAPI(title="Hỏi đáp pháp luật giao thông đường bộ – GraphRAG", version="0.1.0", lifespan=lifespan)

# Chỉ cho phép frontend của nhóm gọi API (địa chỉ Static Site trên Render, cách nhau bởi dấu phẩy)
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.exception_handler(NotImplementedError)
async def not_implemented(_: Request, exc: NotImplementedError):
    return JSONResponse(status_code=501, content={"detail": str(exc) or "Chức năng đang được hoàn thiện"})


@app.get("/health", tags=["hệ thống"])
def health(request: Request):
    """Render gọi định kỳ để biết dịch vụ còn sống. Không chạm tới DB."""
    return {"status": "ok", "env": request.app.state.res.cfg["env"]}


@app.get("/health/db", tags=["hệ thống"])
def health_db(request: Request):
    """Kiểm tra kết nối Supabase/PostgreSQL và AuraDB/Neo4j (dùng khi triển khai, chụp ảnh báo cáo)."""
    return request.app.state.res.check()


for r in (ask.router, documents.router, graph.router, feedback.router, admin.router, system.router):
    app.include_router(r, prefix="/api")
