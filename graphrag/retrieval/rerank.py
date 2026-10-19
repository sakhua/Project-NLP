"""Xếp hạng lại các ứng viên sau bước gộp RRF. Phụ trách: TV3.

  reranker.provider = openrouter (mặc định): gọi API rerank, vd. cohere/rerank-v3.5
  reranker.provider = local                : bge-reranker-v2-m3 chạy trên máy (cần ".[ml]" và GPU)
"""
from __future__ import annotations

_local_model = None


def rerank(cfg: dict, query: str, candidates: list[tuple[str, str]], top_n: int = 10) -> list[tuple[str, float]]:
    """candidates: danh sách (id, nội dung). Trả về (id, điểm) đã sắp xếp giảm dần."""
    r = cfg["reranker"]
    if not candidates:
        return []
    if not r.get("enabled", True):
        return [(cid, 0.0) for cid, _ in candidates[:top_n]]
    if r["provider"] == "openrouter":
        from graphrag.openrouter import get_client

        ranked = get_client(cfg).rerank(r["model"], query, [t for _, t in candidates], top_n)
        return [(candidates[i][0], s) for i, s in ranked]
    if r["provider"] == "local":
        global _local_model
        if _local_model is None:
            from sentence_transformers import CrossEncoder

            _local_model = CrossEncoder(r.get("local_model", "BAAI/bge-reranker-v2-m3"))
        scores = _local_model.predict([(query, t) for _, t in candidates])
        ranked = sorted(zip([c[0] for c in candidates], map(float, scores)), key=lambda x: -x[1])
        return ranked[:top_n]
    raise ValueError(f"reranker.provider không hợp lệ: {r['provider']}")
