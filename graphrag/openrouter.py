"""Client gọi OpenRouter (https://openrouter.ai) cho cả 3 loại mô hình qua một API key:

  chat       POST /api/v1/chat/completions   – sinh câu trả lời, LLM-judge (vd. openai/gpt-4o-mini)
  embeddings POST /api/v1/embeddings         – mã hóa văn bản (vd. baai/bge-m3, 1024 chiều)
  rerank     POST /api/v1/rerank             – xếp hạng lại (vd. cohere/rerank-v3.5)

Đổi mô hình chỉ cần sửa tên trong configs/base.yaml. Khóa đặt ở biến môi trường OPENROUTER_API_KEY.
Nên đặt hạn mức chi tiêu (credit limit) cho API key trong trang quản lý key của OpenRouter.

Hai khóa (OPENAI_API_KEY, OPENROUTER_API_KEY; mặc định OpenAI trước): chat dùng nhà cung cấp đầu tiên trong llm.nha_cung_cap còn
dùng được; khi một khóa hết tiền / hết hạn mức / sai khóa (401, 402, 403, 429 insufficient_quota) thì chuyển sang khóa
kia và không gọi lại khóa đã hết trong suốt tiến trình. Chỉ mô hình "openai/..." mới chạy được trên OpenAI (bỏ tiền tố),
và đó là cùng một mô hình nên kết quả so sánh được. Embedding bge-m3 và rerank Cohere không có trên OpenAI nên vẫn
chỉ đi qua OpenRouter (rất rẻ, nhưng khóa OpenRouter vẫn phải còn hạn mức cho hai việc này).
"""
from __future__ import annotations

import json
import sys
import threading
import time
from collections.abc import Iterator

import httpx

BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_URL = "https://api.openai.com/v1"
RETRY_STATUS = {429, 500, 502, 503}


class OpenRouterError(RuntimeError):
    """Lỗi khi gọi mô hình (OpenRouter hoặc OpenAI). status: mã HTTP nếu có."""

    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


def la_loi_tai_khoan(e: Exception) -> bool:
    """Lỗi về khóa/tài khoản (hết tiền, hết hạn mức khóa, sai khóa): gọi lại cùng khóa chỉ ra cùng lỗi."""
    st, msg = getattr(e, "status", None), str(e).lower()
    if st in (401, 402):          # sai khóa / hết credits
        return True
    if st == 403:                 # OpenRouter cũng trả 403 khi nội dung bị kiểm duyệt: chỉ tính khi báo hết hạn mức
        return any(t in msg for t in ("limit", "credit", "quota"))
    return "insufficient_quota" in msg or "key limit exceeded" in msg or "insufficient credits" in msg


class OpenRouter:
    def __init__(self, api_key: str, timeout: float = 60.0, max_retries: int = 3, app_name: str = "GraphRAG luat GTDB",
                 transport: httpx.BaseTransport | None = None, base_url: str = BASE_URL, ten: str = "openrouter"):
        if not api_key:
            bien = "OPENROUTER_API_KEY" if ten == "openrouter" else f"{ten.upper()}_API_KEY"
            raise OpenRouterError(f"Thiếu {bien} (đặt trong .env hoặc biến môi trường)")
        self.ten = ten
        self.http = httpx.Client(
            base_url=base_url, timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": app_name}, transport=transport,
        )
        self.max_retries = max_retries
        self.backoff = 1.0

    def _post(self, path: str, body: dict) -> dict:
        for attempt in range(self.max_retries + 1):
            r = self.http.post(path, json=body)
            if r.status_code in RETRY_STATUS and attempt < self.max_retries and "insufficient_quota" not in r.text:
                time.sleep(self.backoff * 2 ** attempt)   # chờ 1, 2, 4 giây rồi thử lại
                continue
            if r.status_code >= 400:
                raise OpenRouterError(f"[{self.ten}] {path} lỗi {r.status_code}: {r.text[:300]}", r.status_code)
            return r.json()
        raise OpenRouterError(f"{path}: hết số lần thử lại")

    def chat(self, model: str, system: str, user: str, temperature: float = 0.0, max_tokens: int | None = None) -> str:
        body = {"model": model, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if max_tokens:
            body["max_tokens"] = max_tokens
        data = self._post("/chat/completions", body)
        return data["choices"][0]["message"]["content"] or ""

    def chat_stream(self, model: str, system: str, user: str, temperature: float = 0.0,
                    max_tokens: int | None = None) -> Iterator[str]:
        """Như chat() nhưng trả về từng đoạn chữ ngay khi mô hình sinh ra (giao diện hiện chữ chạy dần)."""
        body = {"model": model, "temperature": temperature, "stream": True,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if max_tokens:
            body["max_tokens"] = max_tokens
        for attempt in range(self.max_retries + 1):
            with self.http.stream("POST", "/chat/completions", json=body) as r:
                if r.status_code >= 400:
                    noi_dung = r.read().decode(errors="replace")
                    if r.status_code in RETRY_STATUS and attempt < self.max_retries and "insufficient_quota" not in noi_dung:
                        time.sleep(self.backoff * 2 ** attempt)
                        continue
                    raise OpenRouterError(f"[{self.ten}] /chat/completions lỗi {r.status_code}: {noi_dung[:300]}",
                                          r.status_code)
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue                  # dòng trống hoặc chú thích ": OPENROUTER PROCESSING"
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    chunk = json.loads(data)
                    if "error" in chunk:
                        err = chunk["error"]
                        code = err.get("code") if isinstance(err, dict) else None
                        raise OpenRouterError(f"[{self.ten}] /chat/completions lỗi: {err}",
                                              code if isinstance(code, int) else None)
                    delta = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                return
        raise OpenRouterError(f"[{self.ten}] /chat/completions: hết số lần thử lại")

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


def _ten_mo_hinh(ten_ncc: str, model: str) -> str | None:
    """Tên mô hình theo từng nhà cung cấp; None nếu nhà cung cấp đó không có mô hình này."""
    if ten_ncc == "openai":
        return model.split("/", 1)[1] if model.startswith("openai/") else (None if "/" in model else model)
    return model


class DuPhong:
    """Nhiều khóa theo thứ tự ưu tiên, cùng giao diện với OpenRouter. Khóa nào gặp lỗi tài khoản thì bỏ qua từ đó về sau."""

    def __init__(self, clients: list[OpenRouter]):
        if not clients:
            raise OpenRouterError("Chưa có khóa API nào: đặt OPENROUTER_API_KEY và/hoặc OPENAI_API_KEY trong .env")
        self.clients = clients
        self.da_het: dict[str, str] = {}          # tên nhà cung cấp → lỗi khiến phải bỏ
        self.dem: dict[str, int] = {c.ten: 0 for c in clients}   # số lượt chat thành công theo nhà cung cấp
        self._lock = threading.Lock()

    def _ung_vien(self, model: str, chi: tuple[str, ...] | None = None):
        out = []
        for c in self.clients:
            m = _ten_mo_hinh(c.ten, model)
            # embedding/rerank (chi=...) chỉ có một nơi gọi được nên vẫn thử, kể cả khi chat đã đánh dấu khóa đó hết
            if m is not None and (chi is not None or c.ten not in self.da_het) and (chi is None or c.ten in chi):
                out.append((c, m))
        if not out:
            ly_do = "; ".join(f"{k}: {v}" for k, v in self.da_het.items()) or "không nhà cung cấp nào có mô hình này"
            raise OpenRouterError(f"Hết khóa dùng được cho {model} ({ly_do})",
                                  403 if self.da_het else None)
        return out

    def _bo(self, c: OpenRouter, e: Exception) -> None:
        with self._lock:
            if c.ten not in self.da_het:
                self.da_het[c.ten] = str(e)[:200]
                con = [x.ten for x in self.clients if x.ten not in self.da_het]
                print(f"\n[LLM] Khóa {c.ten} không dùng được nữa ({str(e)[:120]}). "
                      f"{'Chuyển sang ' + ', '.join(con) if con else 'Không còn khóa dự phòng'}.", file=sys.stderr)

    def _goi(self, model: str, ham, chi=None):
        loi = None
        for c, m in self._ung_vien(model, chi):
            try:
                kq = ham(c, m)
                with self._lock:
                    self.dem[c.ten] = self.dem.get(c.ten, 0) + 1
                return kq
            except OpenRouterError as e:
                if not la_loi_tai_khoan(e):
                    raise
                self._bo(c, e)
                loi = e
        raise loi or OpenRouterError(f"Hết khóa dùng được cho {model}", 403)

    def chat(self, model, system, user, temperature=0.0, max_tokens=None) -> str:
        return self._goi(model, lambda c, m: c.chat(m, system, user, temperature, max_tokens))

    def chat_stream(self, model, system, user, temperature=0.0, max_tokens=None) -> Iterator[str]:
        loi = None
        for c, m in self._ung_vien(model):
            da_ra = False
            try:
                for d in c.chat_stream(m, system, user, temperature, max_tokens):
                    da_ra = True
                    yield d
                with self._lock:
                    self.dem[c.ten] = self.dem.get(c.ten, 0) + 1
                return
            except OpenRouterError as e:
                if da_ra or not la_loi_tai_khoan(e):   # đã hiện chữ cho người dùng thì không đổi giữa chừng
                    raise
                self._bo(c, e)
                loi = e
        raise loi or OpenRouterError(f"Hết khóa dùng được cho {model}", 403)

    # bge-m3 và rerank Cohere chỉ có trên OpenRouter
    def embed(self, model, texts):
        return self._goi(model, lambda c, m: c.embed(m, texts), chi=("openrouter",))

    def rerank(self, model, query, documents, top_n=None):
        return self._goi(model, lambda c, m: c.rerank(m, query, documents, top_n), chi=("openrouter",))

    def close(self) -> None:
        for c in self.clients:
            c.close()


_clients: dict[tuple, DuPhong] = {}


def get_client(cfg: dict) -> DuPhong:
    """Một client dùng chung cho cả tiến trình (giữ kết nối HTTP). Thứ tự khóa theo llm.nha_cung_cap."""
    s = cfg["secrets"]
    khoa = {"openrouter": s.get("openrouter_api_key", ""), "openai": s.get("openai_api_key", "")}
    url = {"openrouter": BASE_URL, "openai": OPENAI_URL}
    thu_tu = tuple(cfg.get("llm", {}).get("nha_cung_cap", ["openai", "openrouter"]))
    k = (thu_tu, tuple(khoa[t] for t in thu_tu if t in khoa))
    if k not in _clients:
        _clients[k] = DuPhong([OpenRouter(khoa[t], base_url=url[t], ten=t) for t in thu_tu if khoa.get(t)])
    return _clients[k]
