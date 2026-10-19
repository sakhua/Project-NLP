"""F3 – Đồ thị liên kết quanh một điều khoản. Phụ trách: TV2."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from graphrag.storage import neo4j_store

from ..deps import get_res

router = APIRouter(tags=["đồ thị"])


@router.get("/graph/{uid}")
def graph(uid: str, res=Depends(get_res)):
    g = neo4j_store.neighbors(res.neo4j, uid)
    if g is None:
        raise HTTPException(status_code=404, detail="Không có node này trong đồ thị")
    return g
