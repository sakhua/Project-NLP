"""F4 – Người dùng đánh giá câu trả lời. Phụ trách: TV2."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from graphrag.storage import postgres

from ..deps import get_res
from ..schemas import FeedbackRequest

router = APIRouter(tags=["đánh giá"])


@router.post("/feedback")
def feedback(body: FeedbackRequest, res=Depends(get_res)):
    if body.rating not in (1, -1):
        raise HTTPException(status_code=422, detail="rating phải là 1 hoặc -1")
    with res.pg_pool.connection() as conn:
        if not postgres.save_feedback(conn, body.log_id, body.rating, body.note):
            raise HTTPException(status_code=404, detail="Không tìm thấy lượt hỏi")
    return {"ok": True}
