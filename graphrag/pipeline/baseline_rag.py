"""Ba hệ thống đối chứng, chạy hoàn toàn trên PostgreSQL. Phụ trách: TV3.

B1: BM25        B2: vector (pgvector)        B3: BM25 + vector, gộp RRF, rerank
Mọi hàm nhận `res` (graphrag.resources.Resources) để dùng chung kết nối và mô hình.
"""
from __future__ import annotations

from datetime import date


def retrieve_b1(res, question: str, k: int) -> list[str]:
    raise NotImplementedError  # TODO(TV3): res.bm25.search


def retrieve_b2(res, question: str, k: int) -> list[str]:
    raise NotImplementedError  # TODO(TV3): res.embedder.encode_queries + postgres.vector_search


def retrieve_b3(res, question: str, k: int) -> list[str]:
    raise NotImplementedError  # TODO(TV3): fusion.rrf([b1, b2]) + rerank (nếu bật)


def answer(res, question: str, system: str = "B3", ngay: date | None = None) -> dict:
    """Trả về cùng dạng với graph_rag.answer."""
    raise NotImplementedError
