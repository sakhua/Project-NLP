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
