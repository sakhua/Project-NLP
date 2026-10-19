"""Gộp nhiều danh sách xếp hạng bằng Reciprocal Rank Fusion (RRF).

score(d) = Σ_r 1 / (k + rank_r(d)),  rank bắt đầu từ 1.
"""
from __future__ import annotations


def rrf(rankings: list[list[str]], k: int = 60, top_n: int | None = None) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    fused = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return fused[:top_n] if top_n else fused
