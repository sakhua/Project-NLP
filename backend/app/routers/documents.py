"""F2 – Tra cứu văn bản theo ngày áp dụng. Phụ trách: TV2."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from graphrag.common.ids import parse_id
from graphrag.storage import neo4j_store, postgres

from ..deps import get_res

router = APIRouter(tags=["tra cứu"])


@router.get("/documents")
def list_documents(res=Depends(get_res)):
    with res.pg_pool.connection() as conn:
        return postgres.list_van_ban(conn)


@router.get("/documents/{van_ban_id}/units")
def document_units(van_ban_id: str, ngay: date | None = Query(default=None, alias="date"),
                   res=Depends(get_res)):
    """Các Điều/Khoản/Điểm của một văn bản còn hiệu lực tại ngày `date` (bỏ trống = hôm nay)."""
    with res.pg_pool.connection() as conn:
        return postgres.list_units_valid(conn, van_ban_id, ngay or date.today())


@router.get("/units/{uid}")
def unit_detail(uid: str, res=Depends(get_res)):
    """Một đơn vị cùng các phiên bản sửa đổi/bổ sung/thay thế của nó (lịch sử hiệu lực)."""
    try:
        parse_id(uid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Mã đơn vị không hợp lệ") from None
    ids = [uid] + neo4j_store.versions(res.neo4j, uid)
    with res.pg_pool.connection() as conn:
        units = postgres.get_units(conn, ids)
    if not any(u["id"] == uid for u in units):
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn vị")
    return {"id": uid, "versions": units}
