"""F5 – Thống kê cho quản trị viên. Phụ trách: TV1."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from graphrag.storage import postgres

from ..deps import get_res, require_admin

router = APIRouter(tags=["quản trị"], dependencies=[Depends(require_admin)])


@router.get("/admin/stats")
def admin_stats(days: int = 30, res=Depends(get_res)):
    with res.pg_pool.connection() as conn:
        return postgres.stats(conn, days=min(max(days, 1), 365))
