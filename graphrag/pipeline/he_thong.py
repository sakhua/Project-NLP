"""Ba hệ thống hỏi đáp dùng chung một giao diện gọi (backend, script đánh giá, giao diện so sánh).

  hybrid_graphrag  Hệ thống đề xuất: tìm kiếm lai BM25 + vector, rerank, mở rộng đồ thị văn bản, lọc theo ngày
  hybrid_rag       B1: chỉ bước tìm kiếm lai + rerank (không đồ thị)
  ms_graphrag      B2: GraphRAG kiểu Microsoft – đồ thị thực thể do LLM trích, cộng đồng Leiden, local/global search
Cả ba dùng cùng mô hình sinh, cùng prompt, cùng cách trích dẫn và cùng bước lọc phiên bản theo ngày.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from graphrag.pipeline import baseline_rag, graph_rag, ms_graphrag

MAC_DINH = "hybrid_graphrag"
HE_THONG = {
    "hybrid_graphrag": {"ten": "Hybrid GraphRAG (đề xuất)", "ma": "GRAPH",
                        "mo_ta": "Tìm kiếm lai BM25 + vector, rerank, mở rộng trên đồ thị văn bản (dẫn chiếu, hướng dẫn)",
                        "steps": graph_rag.STEPS},
    "hybrid_rag": {"ten": "Hybrid RAG (B1)", "ma": "B1",
                   "mo_ta": "Tìm kiếm lai BM25 + vector, gộp RRF, rerank; không dùng đồ thị",
                   "steps": baseline_rag.STEPS},
    "ms_graphrag": {"ten": "GraphRAG kiểu Microsoft (B2)", "ma": "B2",
                    "mo_ta": "Đồ thị thực thể do LLM trích, cộng đồng Leiden, local search (global cho câu hỏi tổng quan)",
                    "steps": ms_graphrag.STEPS},
}


def run(res, question: str, he_thong: str = MAC_DINH, ngay: date | None = None, history: list[dict] | None = None,
        che_do: str = "local", stream: bool = False, use_temporal_filter: bool = True) -> Iterator[dict]:
    if he_thong not in HE_THONG:
        raise ValueError(f"Hệ thống không hợp lệ: {he_thong}. Chọn một trong {list(HE_THONG)}")
    kw = {"ngay": ngay, "history": history, "stream": stream, "use_temporal_filter": use_temporal_filter}
    if he_thong == "ms_graphrag":
        gen = ms_graphrag.run(res, question, che_do=che_do, **kw)
    elif he_thong == "hybrid_rag":
        gen = baseline_rag.run(res, question, **kw)
    else:
        gen = graph_rag.run(res, question, **kw)
    for ev in gen:
        if ev["type"] in ("context", "done"):
            ev["he_thong"] = he_thong
        yield ev


def answer(res, question: str, he_thong: str = MAC_DINH, **kw) -> dict:
    out: dict = {}
    for ev in run(res, question, he_thong=he_thong, **kw):
        if ev["type"] == "done":
            out = {k: v for k, v in ev.items() if k != "type"}
    return out
