"""F2 – Tra cứu văn bản theo ngày áp dụng, tìm điều khoản, lịch sử sửa đổi. Phụ trách: TV2."""
from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from graphrag.common.ids import base_id, parse_id
from graphrag.pipeline.prompts import nhan_ngan, ten_dieu_khoan, ten_van_ban_ngan
from graphrag.retrieval.query_expansion import expand
from graphrag.storage import neo4j_store, postgres

from ..deps import get_res

router = APIRouter(tags=["tra cứu"])

_ID_LIKE = re.compile(r"^[A-Za-z]+\d+_\d{4}", re.I)


def _named(rows: list[dict]) -> list[dict]:
    return [{**r, "ten": ten_dieu_khoan(r["id"]), "nhan": nhan_ngan(r["id"])} for r in rows]


@router.get("/documents")
def list_documents(res=Depends(get_res)):
    with res.pg_pool.connection() as conn:
        return postgres.list_van_ban(conn)


@router.get("/documents/{van_ban_id}/units")
def document_units(van_ban_id: str, ngay: date | None = Query(default=None, alias="date"),
                   res=Depends(get_res)):
    """Các Chương/Điều/Khoản/Điểm của một văn bản còn hiệu lực tại ngày `date` (bỏ trống = hôm nay)."""
    with res.pg_pool.connection() as conn:
        return postgres.list_units_valid(conn, van_ban_id, ngay or date.today())


@router.get("/units/search")
def search_units(q: str = Query(min_length=2, max_length=200), limit: int = Query(default=20, le=50),
                 res=Depends(get_res)):
    """Tìm điều khoản theo mã ('ND168_2024.D6.K9') hoặc theo nội dung (BM25, tiếng Việt có dấu)."""
    q = q.strip()
    with res.pg_pool.connection() as conn:
        if _ID_LIKE.match(q):
            rows = postgres.search_units_by_id(conn, q, limit)
        else:
            ids = []
            for vid, score in res.bm25.search(expand(q), k=limit * 3):
                if score <= 0:
                    break
                i = base_id(vid)
                if i not in ids:
                    ids.append(i)
            rows = postgres.unit_summaries(conn, ids[:limit])
    return _named(rows)


@router.get("/amended")
def amended(res=Depends(get_res)):
    """Các điều khoản đã được sửa đổi, bổ sung, thay thế hoặc bãi bỏ (trang Lịch sử sửa đổi)."""
    with res.pg_pool.connection() as conn:
        rows = postgres.amended_units(conn)
    return [{**r, "van_ban_sua_ten": [ten_van_ban_ngan(v) for v in r["van_ban_sua"]]} for r in _named(rows)]


@router.get("/units/{uid}")
def unit_detail(uid: str, res=Depends(get_res)):
    """Một đơn vị cùng mọi phiên bản của nó (lịch sử hiệu lực) và các văn bản đã sửa đổi nó."""
    try:
        parse_id(uid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Mã đơn vị không hợp lệ") from None
    with res.pg_pool.connection() as conn:
        units = postgres.get_units(conn, [uid])
    if not units:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn vị")
    for v in units:
        v["nguon_ten"] = ten_dieu_khoan(v["nguon_sua_doi"]) if v.get("nguon_sua_doi") else None
    try:
        sua = neo4j_store.amended_by(res.neo4j, [uid])
    except Exception:  # noqa: BLE001 – Neo4j tắt vẫn xem được các phiên bản
        sua = []
    for a in sua:
        a["nguon_ten"] = ten_dieu_khoan(a["nguon"])
    return {"id": uid, "ten": ten_dieu_khoan(uid), "nhan": nhan_ngan(uid), "versions": units, "sua_doi_boi": sua}
