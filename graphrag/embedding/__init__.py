"""Chọn mô hình embedding theo cấu hình (embedding.provider).

  openrouter (mặc định): gọi API, model baai/bge-m3 → cột `embedding` vector(1024)
  local               : chạy bge-m3 trên máy bằng sentence-transformers (cần pip install -e ".[ml]")

Hai cách cho cùng mô hình bge-m3 nên dùng chung một cột; nhưng phải mã hóa kho văn bản và
câu hỏi bằng cùng MỘT cách để kết quả nhất quán.
Mọi embedder có cùng giao diện: .dim, .encode_queries(texts), .encode_documents(texts)
"""
from __future__ import annotations


def get_embedder(cfg: dict):
    e = cfg["embedding"]
    if e["provider"] == "openrouter":
        from graphrag.openrouter import get_client

        from .openrouter import OpenRouterEmbedder

        return OpenRouterEmbedder(get_client(cfg), e["model"], e["dim"], e.get("batch_size", 64))
    if e["provider"] == "local":
        from .local_bge_m3 import BgeM3Embedder

        return BgeM3Embedder(e.get("local_model", "BAAI/bge-m3"), e["dim"], e.get("batch_size", 16))
    raise ValueError(f"embedding.provider không hợp lệ: {e['provider']}")
