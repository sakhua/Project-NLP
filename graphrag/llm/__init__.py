"""Gọi mô hình ngôn ngữ qua OpenRouter: sinh câu trả lời (llm.model) và chấm điểm (evaluation.judge_model)."""
from __future__ import annotations


class LLM:
    def __init__(self, client, model: str, temperature: float = 0.0, max_tokens: int | None = None):
        self.client, self.model, self.temperature, self.max_tokens = client, model, temperature, max_tokens

    def generate(self, system: str, user: str) -> str:
        return self.client.chat(self.model, system, user, self.temperature, self.max_tokens)

    def generate_stream(self, system: str, user: str):
        """Sinh câu trả lời theo từng đoạn chữ (dùng cho /api/ask/stream)."""
        yield from self.client.chat_stream(self.model, system, user, self.temperature, self.max_tokens)


def get_llm(cfg: dict, role: str = "answer") -> LLM:
    """role='answer' dùng llm.model; role='judge' dùng evaluation.judge_model."""
    from graphrag.openrouter import get_client

    c = cfg["llm"]
    if c.get("provider", "openrouter") != "openrouter":
        raise ValueError(f"llm.provider chưa hỗ trợ: {c['provider']}")
    model = c["model"] if role == "answer" else cfg["evaluation"]["judge_model"]
    return LLM(get_client(cfg), model, c.get("temperature", 0.0), c.get("max_tokens"))
