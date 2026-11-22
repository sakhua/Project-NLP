"""Client gọi OpenRouter (https://openrouter.ai) cho cả 3 loại mô hình qua một API key:

  chat       POST /api/v1/chat/completions   – sinh câu trả lời, dựng chỉ mục GraphRAG (vd. openai/gpt-6-luna)
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


def _loi_tham_so(e: "OpenRouterError", ten: str) -> bool:
    """Lỗi 400 vì mô hình không nhận một tham số (vd. temperature với mô hình suy luận)."""
    msg = str(e).lower()
    return getattr(e, "status", None) == 400 and ten in msg and any(
        t in msg for t in ("unsupported", "not supported", "does not support", "only the default", "unrecognized",
                           "invalid"))


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
        self.bo_tham_so: dict[str, set[str]] = {}     # mô hình → tham số đã bị từ chối (không gửi nữa)
        self.usage = {"prompt": 0, "cached": 0, "completion": 0, "reasoning": 0, "calls": 0}
        self._ulock = threading.Lock()

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

    def _body(self, model: str, messages: list[dict], temperature, max_tokens, reasoning_effort) -> dict:
        """OpenAI: max_completion_tokens, reasoning_effort. OpenRouter: max_tokens, reasoning.effort.
        Tham số mô hình đã từ chối một lần (vd. temperature ở mô hình suy luận) thì không gửi nữa."""
        bo = self.bo_tham_so.get(model, set())
        body: dict = {"model": model, "messages": messages}
        if temperature is not None and "temperature" not in bo:
            body["temperature"] = temperature
        if max_tokens:
            body["max_completion_tokens" if self.ten == "openai" else "max_tokens"] = max_tokens
        if reasoning_effort and "reasoning" not in bo:
            if self.ten == "openai":
                body["reasoning_effort"] = reasoning_effort
            else:
                body["reasoning"] = {"effort": reasoning_effort}
        return body

    def _ghi_usage(self, u: dict | None) -> None:
        if not u:
            return
        with self._ulock:
            self.usage["calls"] += 1
            self.usage["prompt"] += u.get("prompt_tokens") or 0
            self.usage["completion"] += u.get("completion_tokens") or 0
            self.usage["cached"] += (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            self.usage["reasoning"] += (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0

    def _thu_bo_tham_so(self, model: str, e: "OpenRouterError", body: dict) -> bool:
        """Nếu lỗi do tham số không được hỗ trợ: ghi nhớ, bỏ tham số đó và báo gọi lại."""
        for ten, khoa in (("temperature", ("temperature",)), ("reasoning", ("reasoning_effort", "reasoning"))):
            if any(k in body for k in khoa) and _loi_tham_so(e, ten):
                self.bo_tham_so.setdefault(model, set()).add(ten)
                print(f"[LLM] {self.ten}/{model} không nhận tham số {ten}: bỏ tham số này.", file=sys.stderr)
                return True
        return False

    def chat_messages(self, model: str, messages: list[dict], temperature: float | None = 0.0,
                      max_tokens: int | None = None, reasoning_effort: str | None = None) -> str:
        """Gọi chat với danh sách tin nhắn tùy ý (hội thoại nhiều lượt, vd. bước gleaning của GraphRAG gốc)."""
        for _ in range(3):
            body = self._body(model, messages, temperature, max_tokens, reasoning_effort)
            try:
                data = self._post("/chat/completions", body)
            except OpenRouterError as e:
                if self._thu_bo_tham_so(model, e, body):
                    continue
                raise
            self._ghi_usage(data.get("usage"))
            return data["choices"][0]["message"].get("content") or ""
        raise OpenRouterError(f"[{self.ten}] {model}: không gọi được sau khi bỏ các tham số không hỗ trợ")

    def chat(self, model: str, system: str, user: str, temperature: float | None = 0.0, max_tokens: int | None = None,
             reasoning_effort: str | None = None) -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        return self.chat_messages(model, msgs, temperature, max_tokens, reasoning_effort)

    def chat_stream(self, model: str, system: str, user: str, temperature: float | None = 0.0,
                    max_tokens: int | None = None, reasoning_effort: str | None = None) -> Iterator[str]:
        """Như chat() nhưng trả về từng đoạn chữ ngay khi mô hình sinh ra (giao diện hiện chữ chạy dần)."""
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        body = self._body(model, msgs, temperature, max_tokens, reasoning_effort)
        body["stream"] = True
        if self.ten == "openai":
            body["stream_options"] = {"include_usage": True}
        for attempt in range(self.max_retries + 1):
            with self.http.stream("POST", "/chat/completions", json=body) as r:
                if r.status_code >= 400:
                    noi_dung = r.read().decode(errors="replace")
                    if r.status_code in RETRY_STATUS and attempt < self.max_retries and "insufficient_quota" not in noi_dung:
                        time.sleep(self.backoff * 2 ** attempt)
                        continue
                    e = OpenRouterError(f"[{self.ten}] /chat/completions lỗi {r.status_code}: {noi_dung[:300]}",
                                        r.status_code)
                    if attempt < self.max_retries and self._thu_bo_tham_so(body["model"], e, body):
                        keep = {k: body[k] for k in ("stream", "stream_options") if k in body}
                        body = {**self._body(model, msgs, temperature, max_tokens, reasoning_effort), **keep}
                        continue
                    raise e
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
                    if chunk.get("usage"):
                        self._ghi_usage(chunk["usage"])
                    delta = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content")
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

    def chat(self, model, system, user, temperature=0.0, max_tokens=None, reasoning_effort=None) -> str:
        return self._goi(model, lambda c, m: c.chat(m, system, user, temperature, max_tokens, reasoning_effort))

    def chat_messages(self, model, messages, temperature=0.0, max_tokens=None, reasoning_effort=None) -> str:
        return self._goi(model, lambda c, m: c.chat_messages(m, messages, temperature, max_tokens, reasoning_effort))

    @property
    def usage(self) -> dict:
        tong = {"prompt": 0, "cached": 0, "completion": 0, "reasoning": 0, "calls": 0}
        for c in self.clients:
            for k in tong:
                tong[k] += c.usage.get(k, 0)
        return tong

    def chat_stream(self, model, system, user, temperature=0.0, max_tokens=None, reasoning_effort=None) -> Iterator[str]:
        loi = None
        for c, m in self._ung_vien(model):
            da_ra = False
            try:
                for d in c.chat_stream(m, system, user, temperature, max_tokens, reasoning_effort):
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
