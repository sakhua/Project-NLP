"""BM25 cho tiếng Việt (tách từ bằng pyvi), dựng từ bảng don_vi.

Phụ trách: TV3.
"""
from __future__ import annotations


def tokenize(text: str) -> list[str]:
    from pyvi import ViTokenizer

    return ViTokenizer.tokenize(text.lower()).split()


class BM25Index:
    def __init__(self, ids: list[str], texts: list[str]):
        from rank_bm25 import BM25Okapi

        self.ids = ids
        self.bm25 = BM25Okapi([tokenize(t) for t in texts])

    def search(self, query: str, k: int = 50) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [(self.ids[i], float(scores[i])) for i in order]
