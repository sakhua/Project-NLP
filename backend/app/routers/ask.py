"""F1 – Hỏi đáp (hội thoại nhiều lượt). Gọi đúng pipeline của môn NLP, chọn hệ thống bằng trường he_thong:
hybrid_graphrag (đề xuất, mặc định) · hybrid_rag (B1) · ms_graphrag (B2, che_do local/global).

POST /api/ask         trả một lần toàn bộ kết quả (dùng cho script, kiểm thử)
POST /api/ask/stream  trả từng dòng JSON (NDJSON): các bước pipeline, ngữ cảnh, từng đoạn chữ, kết quả cuối.
                      Giao diện dùng endpoint này để hiện tiến trình và chữ chạy dần.
"""
from __future__ import annotations

import json
import time
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from graphrag.pipeline import he_thong as ht
from graphrag.storage import postgres

from ..deps import get_res
from ..schemas import AskRequest, AskResponse

router = APIRouter(tags=["hỏi đáp"])


def _log(res, question: str, ngay: date, out: dict, latency_ms: int) -> int | None:
    try:  # ghi nhật ký không được làm hỏng câu trả lời
        ma = ht.HE_THONG.get(out.get("he_thong", ht.MAC_DINH), {}).get("ma", "GRAPH")
        with res.pg_pool.connection() as conn:
            return postgres.log_question(conn, question, ngay, ma, out["answer"], out["citations"], latency_ms)
    except Exception:  # noqa: BLE001
        return None


def friendly_error(e: Exception) -> str:
    """Thông báo lỗi dễ hiểu cho người dùng (chi tiết kỹ thuật xem ở log của backend)."""
    name = type(e).__name__
    msg = str(e)
    if name == "OpenRouterError" or "openrouter" in msg.lower():
        return f"Không gọi được mô hình (OpenRouter/OpenAI): {msg[:200]}"
    if name in ("OperationalError", "PoolTimeout") or "connection" in msg.lower():
        return "Không kết nối được cơ sở dữ liệu. Kiểm tra Docker (PostgreSQL, Neo4j) đã bật chưa."
    return f"Lỗi khi trả lời ({name}). Thử lại sau ít giây."


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, res=Depends(get_res)):
    ngay = body.date or date.today()
    t0 = time.perf_counter()
    out = ht.answer(res, body.question, he_thong=body.he_thong, che_do=body.che_do, ngay=ngay,
                    history=[h.model_dump() for h in body.history])
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return AskResponse(log_id=_log(res, body.question, ngay, out, latency_ms), latency_ms=latency_ms,
                       **{k: v for k, v in out.items() if k in AskResponse.model_fields and k != "latency_ms"})


@router.post("/ask/stream")
def ask_stream(body: AskRequest, res=Depends(get_res)):
    ngay = body.date or date.today()
    history = [h.model_dump() for h in body.history]

    def events():
        t0 = time.perf_counter()
        try:
            for ev in ht.run(res, body.question, he_thong=body.he_thong, che_do=body.che_do, ngay=ngay,
                             history=history, stream=True):
                if ev["type"] == "done":
                    ev["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                    ev["log_id"] = _log(res, body.question, ngay, ev, ev["latency_ms"])
                yield json.dumps(ev, ensure_ascii=False, default=str) + "\n"
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"type": "error", "message": friendly_error(e)}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/systems")
def systems():
    """Danh sách hệ thống để giao diện hiện nút chọn và so sánh."""
    return [{"id": k, "ten": v["ten"], "ma": v["ma"], "mo_ta": v["mo_ta"], "buoc": v["steps"]}
            for k, v in ht.HE_THONG.items()]
