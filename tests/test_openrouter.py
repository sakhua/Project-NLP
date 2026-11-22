"""Kiểm thử client OpenRouter bằng máy chủ giả (không gọi mạng, không tốn tiền)."""
import json

import httpx
import pytest

from graphrag.openrouter import OpenRouter, OpenRouterError


def _client(handler):
    c = OpenRouter("sk-test", transport=httpx.MockTransport(handler))
    c.backoff = 0
    return c


def test_chat_embed_rerank():
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        assert req.headers["authorization"] == "Bearer sk-test"
        if req.url.path.endswith("/chat/completions"):
            assert body["messages"][0]["role"] == "system"
            return httpx.Response(200, json={"choices": [{"message": {"content": "Phạt 18.000.000 đồng [ND168_2024.D6.K9.b]"}}]})
        if req.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": i, "embedding": [float(i), 1.0]} for i in range(len(body["input"]))][::-1]})
        if req.url.path.endswith("/rerank"):
            return httpx.Response(200, json={"model": body["model"], "results": [
                {"index": 1, "relevance_score": 0.9, "document": {"text": body["documents"][1]}},
                {"index": 0, "relevance_score": 0.2, "document": {"text": body["documents"][0]}}]})
        return httpx.Response(404)

    c = _client(handler)
    assert "ND168_2024.D6.K9.b" in c.chat("openai/gpt-4o-mini", "sys", "q")
    assert c.embed("baai/bge-m3", ["a", "b"]) == [[0.0, 1.0], [1.0, 1.0]]   # sắp lại theo index
    assert c.rerank("cohere/rerank-v3.5", "q", ["x", "y"]) == [(1, 0.9), (0, 0.2)]


def test_retry_then_error():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, json={"error": "rate limit"})

    with pytest.raises(OpenRouterError):
        _client(handler).chat("m", "s", "u")
    assert calls["n"] == 4          # 1 lần đầu + 3 lần thử lại


def test_missing_key():
    with pytest.raises(OpenRouterError):
        OpenRouter("")


def _ncc(ten, handler):
    from graphrag.openrouter import OPENAI_URL
    c = OpenRouter("sk-" + ten, transport=httpx.MockTransport(handler), ten=ten,
                   base_url=OPENAI_URL if ten == "openai" else "https://openrouter.ai/api/v1")
    c.backoff = 0
    return c


def test_du_phong_chuyen_sang_openai_khi_het_han_muc():
    from graphrag.openrouter import DuPhong

    goi = {"openrouter": 0, "openai": 0}

    def or_handler(req):
        goi["openrouter"] += 1
        if req.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})
        return httpx.Response(403, json={"error": {"message": "Key limit exceeded", "code": 403}})

    def oa_handler(req):
        goi["openai"] += 1
        assert req.url.host == "api.openai.com"
        assert json.loads(req.content)["model"] == "gpt-4o-mini"      # bỏ tiền tố openai/
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    c = DuPhong([_ncc("openrouter", or_handler), _ncc("openai", oa_handler)])
    assert c.chat("openai/gpt-4o-mini", "s", "u") == "ok"
    assert c.chat("openai/gpt-4o-mini", "s", "u") == "ok"
    assert goi["openrouter"] == 1          # khóa đã hết không bị gọi lại
    assert c.dem == {"openrouter": 0, "openai": 2}
    assert c.embed("baai/bge-m3", ["a"]) == [[1.0]]   # embedding vẫn qua OpenRouter


def test_du_phong_openai_het_quota_thi_quay_ve_openrouter_va_het_ca_hai():
    from graphrag.openrouter import DuPhong

    def oa_handler(req):
        return httpx.Response(429, json={"error": {"type": "insufficient_quota", "code": "insufficient_quota"}})

    def or_handler(req):
        return httpx.Response(200, json={"choices": [{"message": {"content": "or"}}]})

    c = DuPhong([_ncc("openai", oa_handler), _ncc("openrouter", or_handler)])
    assert c.chat("openai/gpt-4o-mini", "s", "u") == "or"
    c2 = DuPhong([_ncc("openai", oa_handler)])
    with pytest.raises(OpenRouterError):
        c2.chat("openai/gpt-4o-mini", "s", "u")
    with pytest.raises(OpenRouterError, match="Hết khóa"):
        c2.chat("openai/gpt-4o-mini", "s", "u")


def test_du_phong_loi_thuong_khong_chuyen_va_mo_hinh_khong_co_tren_openai():
    from graphrag.openrouter import DuPhong

    def or_handler(req):
        return httpx.Response(400, json={"error": "bad request"})

    oa = {"n": 0}

    def oa_handler(req):
        oa["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    c = DuPhong([_ncc("openrouter", or_handler), _ncc("openai", oa_handler)])
    with pytest.raises(OpenRouterError):
        c.chat("openai/gpt-4o-mini", "s", "u")          # lỗi 400 không phải lỗi tài khoản
    assert oa["n"] == 0 and not c.da_het
    with pytest.raises(OpenRouterError):
        c.chat("google/gemini-2.5-flash", "s", "u")     # OpenAI không có mô hình này
    assert oa["n"] == 0


def test_du_phong_stream():
    from graphrag.openrouter import DuPhong

    def or_handler(req):
        return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})

    def oa_handler(req):
        body = "".join(f'data: {json.dumps({"choices": [{"delta": {"content": t}}]})}\n\n' for t in ["Phạt ", "18 triệu"])
        return httpx.Response(200, text=body + "data: [DONE]\n\n")

    c = DuPhong([_ncc("openrouter", or_handler), _ncc("openai", oa_handler)])
    assert "".join(c.chat_stream("openai/gpt-4o-mini", "s", "u")) == "Phạt 18 triệu"


def test_get_client_chi_co_mot_khoa():
    from graphrag.openrouter import get_client

    c = get_client({"secrets": {"openrouter_api_key": "", "openai_api_key": "sk-x"}, "llm": {}})
    assert [x.ten for x in c.clients] == ["openai"]


def test_tham_so_theo_nha_cung_cap_va_tu_bo_temperature():
    """OpenAI: max_completion_tokens, reasoning_effort; mô hình không nhận temperature thì bỏ và ghi nhớ."""
    bodies = []

    def oa_handler(req):
        b = json.loads(req.content)
        bodies.append(b)
        if "temperature" in b:
            return httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature' does not support 0 "
                                                                  "with this model. Only the default (1) value is supported."}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 20,
                                                   "prompt_tokens_details": {"cached_tokens": 40},
                                                   "completion_tokens_details": {"reasoning_tokens": 5}}})

    c = _ncc("openai", oa_handler)
    assert c.chat("gpt-6-luna", "s", "u", 0.0, 500, "low") == "ok"
    assert bodies[-1]["max_completion_tokens"] == 500 and bodies[-1]["reasoning_effort"] == "low"
    assert "max_tokens" not in bodies[-1]
    n = len(bodies)
    assert c.chat("gpt-6-luna", "s", "u") == "ok" and len(bodies) == n + 1      # lần sau không gửi temperature nữa
    assert c.usage == {"prompt": 200, "cached": 80, "completion": 40, "reasoning": 10, "calls": 2}

    or_bodies = []

    def or_handler(req):
        or_bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _ncc("openrouter", or_handler).chat("openai/gpt-6-luna", "s", "u", 0.0, 300, "low")
    assert or_bodies[0]["max_tokens"] == 300 and or_bodies[0]["reasoning"] == {"effort": "low"}


def test_chat_messages_nhieu_luot():
    from graphrag.openrouter import DuPhong

    def handler(req):
        msgs = json.loads(req.content)["messages"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "/".join(m["role"] for m in msgs)}}]})

    c = DuPhong([_ncc("openai", handler)])
    out = c.chat_messages("openai/gpt-6-luna", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                                                {"role": "user", "content": "c"}])
    assert out == "user/assistant/user"
