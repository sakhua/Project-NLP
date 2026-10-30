"""Số liệu tổng quan về kho dữ liệu và đồ thị (thanh bên, trang Thống kê). Công khai, không cần mật khẩu."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from graphrag.storage import neo4j_store, postgres

from ..deps import get_res

router = APIRouter(tags=["hệ thống"])


@router.get("/overview")
def overview(res=Depends(get_res)):
    out = {}
    with res.pg_pool.connection() as conn:
        out["postgres"] = postgres.overview(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM hoi_dap_log")
            out["so_cau_hoi"] = cur.fetchone()[0]
    try:
        out["neo4j"] = neo4j_store.graph_counts(res.neo4j)
    except Exception as e:  # noqa: BLE001
        out["neo4j"] = {"error": type(e).__name__}
    cfg = res.cfg
    out["mo_hinh"] = {"llm": cfg["llm"]["model"], "embedding": cfg["embedding"]["model"],
                      "reranker": cfg["reranker"]["model"] if cfg["reranker"].get("enabled", True) else None}
    return out
