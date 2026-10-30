"""Hội thoại nhiều lượt: viết lại câu hỏi tiếp nối thành câu hỏi đầy đủ trước khi tìm kiếm.

Ví dụ: lượt trước hỏi "Ô tô vượt đèn đỏ bị phạt bao nhiêu?", lượt này hỏi "Còn xe máy thì sao?"
→ "Xe máy vượt đèn đỏ bị phạt bao nhiêu?". Tìm kiếm và đồ thị chỉ chạy trên câu đã viết lại;
câu trả lời vẫn chỉ dựa trên NGỮ CẢNH như mọi câu hỏi khác.
"""
from __future__ import annotations

import re

SYSTEM = """Bạn viết lại câu hỏi mới nhất của người dùng thành MỘT câu hỏi đầy đủ, tự hiểu được mà không cần đọc \
hội thoại trước, về pháp luật giao thông đường bộ Việt Nam.
Quy tắc:
- Bổ sung đối tượng, phương tiện, hành vi còn thiếu lấy từ hội thoại (ví dụ "còn xe máy thì sao?" → nêu rõ hành vi đang bàn).
- Giữ nguyên ý định của người dùng, không thêm thông tin mới, không trả lời câu hỏi.
- Nếu câu hỏi mới đã đầy đủ hoặc chuyển sang chủ đề khác, chép lại nguyên văn.
- Chỉ in ra câu hỏi đã viết lại, không giải thích."""

_CITE = re.compile(r"\[[^\[\]]{3,200}\]")


def _clean(text: str, limit: int) -> str:
    text = _CITE.sub("", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def build_prompt(history: list[dict], question: str, turns: int = 3) -> str:
    """history: [{role: 'user'|'assistant', content}] theo thứ tự thời gian; chỉ lấy `turns` lượt gần nhất."""
    msgs = [m for m in history if m.get("role") in ("user", "assistant") and m.get("content")][-2 * turns:]
    lines = []
    for m in msgs:
        who = "Người dùng" if m["role"] == "user" else "Trợ lý"
        lines.append(f"{who}: {_clean(m['content'], 300 if m['role'] == 'user' else 500)}")
    return "HỘI THOẠI TRƯỚC:\n" + "\n".join(lines) + f"\n\nCÂU HỎI MỚI: {question.strip()}\n\nCÂU HỎI ĐẦY ĐỦ:"


def rewrite_question(llm, history: list[dict] | None, question: str, turns: int = 3) -> str:
    """Không có lịch sử thì trả lại nguyên câu hỏi (không gọi LLM)."""
    if not history or not any(m.get("role") == "user" for m in history):
        return question.strip()
    out = llm.generate(SYSTEM, build_prompt(history, question, turns)).strip().strip('"').strip()
    out = out.splitlines()[0].strip() if out else ""
    return out if len(out) >= 5 else question.strip()
