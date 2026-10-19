"""GraphRAG đề xuất. Phụ trách: TV1.

1. Seed: BM25 (res.bm25) + vector (res.embedder + postgres.vector_search), gộp RRF,
   rerank top_k_rerank ứng viên (retrieval.rerank.rerank(cfg, ...), mô hình qua OpenRouter)
2. Mở rộng đồ thị + chuỗi phiên bản (neo4j_store.expand, driver res.neo4j)
3. Lọc theo ngày áp dụng (postgres.fetch_valid)
4. Ghép ngữ cảnh (prompts.format_context) và gọi res.llm.generate(SYSTEM, USER_TEMPLATE...) (llm.model)

Cùng một hàm dùng cho môn NLP (chạy đánh giá) và backend trên cloud.
Các cờ dùng cho ablation: use_amendments, use_references, use_temporal_filter, hops.
"""
from __future__ import annotations

from datetime import date


def answer(res, question: str, ngay: date | None = None, hops: int | None = None,
           use_amendments: bool = True, use_references: bool = True,
           use_temporal_filter: bool = True) -> dict:
    """res: graphrag.resources.Resources.

    Trả về {'answer': str, 'citations': [mã], 'units': [dict đơn vị trong ngữ cảnh],
            'retrieved_ids': [mã], 'latency_s': float}
    """
    raise NotImplementedError("GraphRAG chưa hoàn thiện (TV1, tuần 4–6)")
