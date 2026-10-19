"""Kiểm thử API không cần DB: chạy được trên GitHub Actions."""
from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_and_not_ready_endpoints():
    with TestClient(app) as client:  # "with" để chạy lifespan (tạo Resources)
        r = client.get("/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"

        r = client.post("/api/ask", json={"question": "Ô tô vượt đèn đỏ bị phạt bao nhiêu?"})
        assert r.status_code == 501          # pipeline GraphRAG chưa hoàn thiện

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
