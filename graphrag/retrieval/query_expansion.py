"""Mở rộng câu hỏi bằng từ điển "cách nói thông thường → thuật ngữ trong văn bản" (chỉ dùng cho BM25).

Người dân hỏi "vượt đèn đỏ", "xe máy", "bằng lái"; văn bản viết "không chấp hành hiệu lệnh của đèn tín hiệu
giao thông", "xe mô tô, xe gắn máy", "giấy phép lái xe". BM25 khớp theo từ nên bỏ lỡ; tìm kiếm vector và
rerank hiểu được nghĩa nhưng thêm thuật ngữ vào câu hỏi BM25 giúp seed ổn định hơn.
Chỉ THÊM thuật ngữ vào cuối câu hỏi, không thay câu hỏi gốc (câu gửi cho embedding, rerank, LLM giữ nguyên).
"""
from __future__ import annotations

import re

# cách nói thường gặp (chữ thường) -> thuật ngữ trong NĐ 168/2024, Luật 36/2024, TT 38/2024
SYNONYMS: dict[str, str] = {
    "vượt đèn đỏ": "không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
    "vượt đèn vàng": "không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
    "đèn đỏ": "hiệu lệnh của đèn tín hiệu giao thông",
    "xe máy": "xe mô tô xe gắn máy",
    "ô tô": "xe ô tô",
    "bằng lái": "giấy phép lái xe",
    "trừ điểm": "trừ điểm giấy phép lái xe",
    "tước bằng": "tước quyền sử dụng giấy phép lái xe",
    "rượu bia": "nồng độ cồn trong máu hoặc hơi thở",
    "uống rượu": "nồng độ cồn trong máu hoặc hơi thở",
    "uống bia": "nồng độ cồn trong máu hoặc hơi thở",
    "say xỉn": "nồng độ cồn trong máu hoặc hơi thở",
    "chạy quá tốc độ": "chạy quá tốc độ quy định",
    "quá tốc độ": "chạy quá tốc độ quy định",
    "tốc độ tối đa": "tốc độ khai thác tối đa",
    "không đội mũ": "không đội mũ bảo hiểm cho người đi mô tô, xe máy",
    "mũ bảo hiểm": "đội mũ bảo hiểm cho người đi mô tô, xe máy cài quai đúng quy cách",
    "điện thoại": "dùng tay cầm và sử dụng điện thoại hoặc các thiết bị điện tử khác",
    "ngồi ghế trước": "ngồi cùng hàng ghế với người lái xe",
    "ghế trước": "cùng hàng ghế với người lái xe",
    "trẻ em": "trẻ em dưới 10 tuổi và chiều cao dưới 1,35 mét",
    "đi ngược chiều": "đi ngược chiều của đường một chiều",
    "lấn làn": "đi không đúng phần đường hoặc làn đường quy định",
    "đỗ xe sai": "đỗ xe không đúng quy định",
    "cao tốc": "đường cao tốc",
    "khu dân cư": "khu vực đông dân cư",
    "phục hồi điểm": "phục hồi điểm giấy phép lái xe",
    "hết điểm": "bị trừ hết điểm giấy phép lái xe",
}

_PATTERNS = [(re.compile(r"(?<!\w)" + re.escape(k) + r"(?!\w)", re.I), v) for k, v in
             sorted(SYNONYMS.items(), key=lambda kv: -len(kv[0]))]


def expand(question: str) -> str:
    """Trả về câu hỏi + các thuật ngữ tương ứng (không trùng lặp). Không khớp gì thì trả nguyên câu."""
    extra = []
    for pat, term in _PATTERNS:
        if pat.search(question) and term not in extra and term.lower() not in question.lower():
            extra.append(term)
    return question if not extra else f"{question} {' '.join(extra)}"
