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
