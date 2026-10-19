"""Client gọi OpenRouter (https://openrouter.ai) cho cả 3 loại mô hình qua một API key:

  chat       POST /api/v1/chat/completions   – sinh câu trả lời, LLM-judge (vd. openai/gpt-4o-mini)
  embeddings POST /api/v1/embeddings         – mã hóa văn bản (vd. baai/bge-m3, 1024 chiều)
  rerank     POST /api/v1/rerank             – xếp hạng lại (vd. cohere/rerank-v3.5)

Đổi mô hình chỉ cần sửa tên trong configs/base.yaml. Khóa đặt ở biến môi trường OPENROUTER_API_KEY.
Nên đặt hạn mức chi tiêu (credit limit) cho API key trong trang quản lý key của OpenRouter.
"""
from __future__ import annotations

import time

import httpx

BASE_URL = "https://openrouter.ai/api/v1"
RETRY_STATUS = {429, 500, 502, 503}


class OpenRouterError(RuntimeError):
    pass


class OpenRouter:
    def __init__(self, api_key: str, timeout: float = 60.0, max_retries: int = 3, app_name: str = "GraphRAG luat GTDB",
                 transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise OpenRouterError("Thiếu OPENROUTER_API_KEY (đặt trong .env hoặc biến môi trường)")
        self.http = httpx.Client(
            base_url=BASE_URL, timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": app_name}, transport=transport,
        )
        self.max_retries = max_retries
        self.backoff = 1.0

    def _post(self, path: str, body: dict) -> dict:
        for attempt in range(self.max_retries + 1):
            r = self.http.post(path, json=body)
            if r.status_code in RETRY_STATUS and attempt < self.max_retries:
                time.sleep(self.backoff * 2 ** attempt)   # chờ 1, 2, 4 giây rồi thử lại
                continue
            if r.status_code >= 400:
                raise OpenRouterError(f"{path} lỗi {r.status_code}: {r.text[:300]}")
            return r.json()
        raise OpenRouterError(f"{path}: hết số lần thử lại")

    def chat(self, model: str, system: str, user: str, temperature: float = 0.0, max_tokens: int | None = None) -> str:
        body = {"model": model, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if max_tokens:
            body["max_tokens"] = max_tokens
        data = self._post("/chat/completions", body)
        return data["choices"][0]["message"]["content"] or ""

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        data = self._post("/embeddings", {"model": model, "input": texts})
        items = sorted(data["data"], key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in items]

    def rerank(self, model: str, query: str, documents: list[str], top_n: int | None = None) -> list[tuple[int, float]]:
        body = {"model": model, "query": query, "documents": documents}
        if top_n:
            body["top_n"] = top_n
        data = self._post("/rerank", body)
        return [(r["index"], float(r["relevance_score"])) for r in data["results"]]

    def close(self) -> None:
        self.http.close()


_clients: dict[str, OpenRouter] = {}


def get_client(cfg: dict) -> OpenRouter:
    """Một client dùng chung cho cả tiến trình (giữ kết nối HTTP)."""
    key = cfg["secrets"]["openrouter_api_key"]
    if key not in _clients:
        _clients[key] = OpenRouter(key)
    return _clients[key]
