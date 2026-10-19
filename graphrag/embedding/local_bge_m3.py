"""Embedding bằng bge-m3 chạy trên máy (tùy chọn, khi muốn tránh gọi API). Phụ trách: TV3.

Cần cài thêm nhóm thư viện ml:  pip install -e ".[ml]"  và nên có GPU.
"""
from __future__ import annotations

import numpy as np


class BgeM3Embedder:
    def __init__(self, model: str = "BAAI/bge-m3", dim: int = 1024, batch_size: int = 16):
        self.model_name, self.dim, self.batch_size = model, dim, batch_size
        self._model = None

    def _get(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _encode(self, texts: list[str]) -> np.ndarray:
        return self._get().encode(texts, batch_size=self.batch_size, normalize_embeddings=True)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)
