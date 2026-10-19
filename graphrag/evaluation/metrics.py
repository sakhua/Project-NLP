"""Độ đo truy xuất và câu trả lời. Phụ trách: TV3.

Truy xuất: recall@k, full_recall@k, mrr@k, f2@k (tự viết, khớp cách tính của ALQAC/VLSP).
Câu trả lời: key_fact_accuracy (so khớp số tiền, số điểm), citation P/R.
"""
from __future__ import annotations

import re


def recall_at_k(gold: list[str], retrieved: list[str], k: int) -> float:
    if not gold:
        return 0.0
    return len(set(gold) & set(retrieved[:k])) / len(set(gold))


def full_recall_at_k(gold: list[str], retrieved: list[str], k: int) -> float:
    """1 nếu lấy được TẤT CẢ điều khoản cần thiết trong top-k, ngược lại 0."""
    return float(bool(gold) and set(gold) <= set(retrieved[:k]))


def mrr_at_k(gold: list[str], retrieved: list[str], k: int) -> float:
    g = set(gold)
    for rank, d in enumerate(retrieved[:k], start=1):
        if d in g:
            return 1.0 / rank
    return 0.0


def f2_at_k(gold: list[str], retrieved: list[str], k: int) -> float:
    top = retrieved[:k]
    hit = len(set(gold) & set(top))
    if hit == 0 or not top:
        return 0.0
    p, r = hit / len(top), hit / len(set(gold))
    return 5 * p * r / (4 * p + r)


# ---- Chuẩn hóa số tiền tiếng Việt cho Key-fact Accuracy ----
_UNIT = {"triệu": 1_000_000, "nghìn": 1_000, "ngàn": 1_000, "tỷ": 1_000_000_000, "tỉ": 1_000_000_000}
_MONEY_RE = re.compile(r"(\d+(?:[.,]\d+)*)\s*(triệu|nghìn|ngàn|tỷ|tỉ)?\s*(?:đồng|đ\b)?", re.IGNORECASE)


def _to_number(num: str, unit: str | None) -> int:
    if unit:
        value = float(num.replace(".", "").replace(",", ".")) if num.count(",") == 1 and "." not in num \
            else float(num.replace(",", "."))
        return int(round(value * _UNIT[unit.lower()]))
    return int(num.replace(".", "").replace(",", ""))


def extract_amounts(text: str) -> set[int]:
    """Trích các số tiền (đồng) trong câu trả lời: '12 triệu', '12.000.000 đồng', '1,5 triệu'."""
    out = set()
    for m in _MONEY_RE.finditer(text):
        num, unit = m.group(1), m.group(2)
        try:
            v = _to_number(num, unit)
        except ValueError:
            continue
        if v >= 1000:
            out.add(v)
    return out


def key_fact_accuracy(gold_amounts: set[int], answer: str) -> float:
    """1 nếu mọi số tiền trong đáp án chuẩn đều xuất hiện trong câu trả lời."""
    return float(bool(gold_amounts) and gold_amounts <= extract_amounts(answer))


def citation_pr(gold: list[str], cited: list[str]) -> tuple[float, float]:
    g, c = set(gold), set(cited)
    if not c:
        return 0.0, 0.0
    hit = len(g & c)
    return hit / len(c), (hit / len(g) if g else 0.0)
