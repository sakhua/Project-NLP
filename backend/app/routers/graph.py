"""F3 – Đồ thị liên kết quanh một điều khoản (trang Khám phá đồ thị). Phụ trách: TV2."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from graphrag.pipeline.prompts import nhan_ngan, ten_dieu_khoan
from graphrag.storage import neo4j_store

from ..deps import get_res

router = APIRouter(tags=["đồ thị"])


@router.get("/graph/{uid}")
def graph(uid: str, limit: int = Query(default=60, ge=5, le=200), res=Depends(get_res)):
    g = neo4j_store.neighbors(res.neo4j, uid, limit=limit)
    if g is None:
        raise HTTPException(status_code=404, detail="Không có node này trong đồ thị")
    for n in [g["center"], *g["neighbors"]]:
        n["nhan"] = nhan_ngan(n["id"])
        n["ten"] = ten_dieu_khoan(n["id"])
    return g
