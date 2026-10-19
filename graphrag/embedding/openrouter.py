"""Embedding qua OpenRouter (mặc định baai/bge-m3, 1024 chiều) – dùng cho cả máy nhóm và cloud.

Không cần GPU hay tải mô hình vài GB, nên chạy được trên máy chủ Render 512 MB.
Quan trọng: kho văn bản và câu hỏi phải được mã hóa bằng CÙNG một mô hình.
"""
from __future__ import annotations

import numpy as np


class OpenRouterEmbedder:
    def __init__(self, client, model: str = "baai/bge-m3", dim: int = 1024, batch_size: int = 64):
        self.client, self.model, self.dim, self.batch_size = client, model, dim, batch_size

    def _encode(self, texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out.extend(self.client.embed(self.model, texts[i:i + self.batch_size]))
        arr = np.asarray(out, dtype=np.float32)
        if arr.shape[1] != self.dim:
            raise ValueError(f"{self.model} trả về {arr.shape[1]} chiều, cấu hình là {self.dim}")
        return arr / np.linalg.norm(arr, axis=1, keepdims=True).clip(min=1e-12)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)
