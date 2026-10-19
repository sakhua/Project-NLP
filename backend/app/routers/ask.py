"""F1 – Hỏi đáp. Gọi đúng pipeline GraphRAG của môn NLP."""
from __future__ import annotations

import time
from datetime import date

from fastapi import APIRouter, Depends

from graphrag.pipeline import graph_rag
from graphrag.storage import postgres

from ..deps import get_res
from ..schemas import AskRequest, AskResponse

router = APIRouter(tags=["hỏi đáp"])


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, res=Depends(get_res)):
    ngay = body.date or date.today()
    t0 = time.perf_counter()
    out = graph_rag.answer(res, body.question, ngay=ngay)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    log_id = None
    try:  # ghi nhật ký không được làm hỏng câu trả lời
        with res.pg_pool.connection() as conn:
            log_id = postgres.log_question(conn, body.question, ngay, "GRAPH", out["answer"],
                                           out["citations"], latency_ms)
    except Exception:  # noqa: BLE001
        pass
    return AskResponse(log_id=log_id, answer=out["answer"], citations=out["citations"],
                       units=out["units"], date=ngay, latency_ms=latency_ms)
