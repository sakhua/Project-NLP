"""Kiểm thử API không cần DB: chạy được trên GitHub Actions."""
from fastapi.testclient import TestClient

from backend.app.main import app


def _mo(client):
    """Các kiểm thử dưới đây chạy khi tắt đăng nhập (auth.bat_buoc = false)."""
    client.app.state.res.cfg["auth"]["bat_buoc"] = False
    return client


def test_health_and_not_ready_endpoints():
    with TestClient(app) as client:  # "with" để chạy lifespan (tạo Resources)
        _mo(client)
        r = client.get("/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"

        r = client.post("/api/ask", json={"question": "?"})
        assert r.status_code == 422          # câu hỏi quá ngắn

        r = client.get("/api/admin/stats")
        assert r.status_code == 401          # thiếu mật khẩu quản trị


def test_config_profiles():
    from graphrag.common.config import load_config

    local, cloud = load_config("local"), load_config("cloud")
    for c in (local, cloud):                            # hai môi trường dùng chung mô hình qua OpenRouter
        assert c["embedding"]["provider"] == "openrouter" and c["embedding"]["dim"] == 1024
        assert c["reranker"]["provider"] == "openrouter" and c["llm"]["provider"] == "openrouter"
    assert local["retrieval"] == cloud["retrieval"]
    assert cloud["llm"]["max_tokens"] == 800


def test_ask_stream_ndjson(monkeypatch):
    import json

    from graphrag.pipeline import graph_rag

    def fake_run(res, question, ngay=None, history=None, stream=False, **kw):
        assert history == [{"role": "user", "content": "Ô tô vượt đèn đỏ?"}]
        yield {"type": "step", "key": "search", "label": "x", "ms": 1, "detail": "d"}
        yield {"type": "token", "text": "Phạt "}
        yield {"type": "done", "answer": "Phạt", "citations": [], "units": [], "graph": {"nodes": [], "edges": []}}

    monkeypatch.setattr(graph_rag, "run", fake_run)
    with TestClient(app) as client:
        _mo(client)
        r = client.post("/api/ask/stream", json={"question": "Còn xe máy thì sao?", "date": "2026-09-01",
                                                 "history": [{"role": "user", "content": "Ô tô vượt đèn đỏ?"}]})
        lines = [json.loads(x) for x in r.text.splitlines()]
        assert [e["type"] for e in lines] == ["step", "token", "done"]
        assert "latency_ms" in lines[-1] and "log_id" in lines[-1]


def test_ask_stream_reports_error(monkeypatch):
    import json

    from graphrag.pipeline import graph_rag

    def broken(*a, **k):
        raise ConnectionError("connection refused")
        yield  # noqa

    monkeypatch.setattr(graph_rag, "run", broken)
    with TestClient(app) as client:
        _mo(client)
        r = client.post("/api/ask/stream", json={"question": "Ô tô vượt đèn đỏ?"})
        ev = json.loads(r.text.splitlines()[-1])
        assert ev["type"] == "error" and "Docker" in ev["message"]
