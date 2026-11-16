"""B1 – Hybrid RAG: hệ thống đối chứng chỉ có bước truy hồi đầu của hệ thống đề xuất.

BM25 (+ mở rộng truy vấn) và vector (pgvector) → gộp RRF → lọc theo ngày áp dụng → rerank → top_k_final
→ cùng prompt và cách trích dẫn với hệ thống đề xuất. KHÔNG mở rộng đồ thị.

Dùng lại đúng mã của graph_rag.run với hops = 0, nên khác biệt giữa B1 và hệ thống đề xuất chỉ là bước
mở rộng trên đồ thị (so sánh công bằng, cũng chính là thí nghiệm ablation "bỏ đồ thị").
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from graphrag.pipeline import graph_rag

STEPS = {k: v for k, v in graph_rag.STEPS.items() if k != "graph"}


def run(res, question: str, ngay: date | None = None, history: list[dict] | None = None,
        use_temporal_filter: bool = True, stream: bool = False, **_) -> Iterator[dict]:
    """Phát sự kiện cùng dạng graph_rag.run (step / context / token / done)."""
    yield from graph_rag.run(res, question, ngay=ngay, history=history, hops=0,
                             use_temporal_filter=use_temporal_filter, stream=stream)


def answer(res, question: str, ngay: date | None = None, history: list[dict] | None = None,
           use_temporal_filter: bool = True, **_) -> dict:
    """Trả về cùng dạng với graph_rag.answer."""
    out: dict = {}
    for ev in run(res, question, ngay=ngay, history=history, use_temporal_filter=use_temporal_filter):
        if ev["type"] == "done":
            out = {k: v for k, v in ev.items() if k != "type"}
    return out
