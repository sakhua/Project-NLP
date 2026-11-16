"""Độ đo truy xuất và câu trả lời. Phụ trách: TV3.

Bộ độ đo dùng trong đề tài (chỉ 6 độ đo, không dùng LLM chấm; định nghĩa: docs/do_do_danh_gia.md):
  Truy xuất: recall_at_k, full_recall_at_k, mrr_at_k, f2_at_k (tự viết, khớp cách tính của ALQAC/VLSP).
  Câu trả lời: faithfulness_khong_llm, answer_relevance_khong_llm.
Các hàm key_fact_accuracy, citation_pr giữ lại cho scripts/thu_prompt.py, không đưa vào báo cáo.
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


# ---------------------------------------------------------------- Faithfulness, Answer Relevance KHÔNG dùng LLM
# Thay cho bản LLM-judge của RAGAS: tách các "dữ kiện kiểm chứng được" trong câu trả lời (mức tiền, số điểm trừ,
# mã điều khoản được trích) rồi so khớp bằng quy tắc. Tất định, không tốn API, lặp lại được.

def so_tien_trong(text: str) -> set[int]:
    """Mức tiền (đồng): '18.000.000', '18 triệu', 'từ 18 đến 20 triệu', '1,5 triệu', '500 nghìn'."""
    t = (text or "").replace(" ", " ")
    out = {int(x.replace(".", "").replace(",", "")) for x in re.findall(r"\d{1,3}(?:[.,]\d{3})+(?![.,]?\d)", t)}

    def num(s: str) -> float:
        return float(s.replace(",", "."))

    for a, b, dv in re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:đến|–|-|tới)\s*(\d+(?:[.,]\d+)?)\s*(triệu|nghìn|ngàn)", t):
        k = 1_000_000 if dv == "triệu" else 1_000
        out |= {round(num(a) * k), round(num(b) * k)}
    for a, dv in re.findall(r"(\d+(?:[.,]\d+)?)\s*(triệu|nghìn|ngàn)", t):
        out.add(round(num(a) * (1_000_000 if dv == "triệu" else 1_000)))
    return {x for x in out if x >= 1000}


def so_diem_trong(text: str) -> set[int]:
    """Số điểm giấy phép lái xe: '04 điểm', 'trừ 6 điểm', '12 điểm' (không nhầm với 'điểm b khoản 9')."""
    return {int(x) for x in re.findall(r"(?<![\d.,])(\d{1,2})\s*điểm\b", text or "")}


def du_kien(text: str) -> set[tuple[str, int]]:
    return {("tien", x) for x in so_tien_trong(text)} | {("diem", x) for x in so_diem_trong(text)}


_PHU_DINH = re.compile(r"chưa (bị|có|áp dụng|được)|không (bị|có quy định|áp dụng|thuộc)|hết hiệu lực|chưa có hiệu lực",
                       re.IGNORECASE)


def faithfulness_khong_llm(answer: str, context: list[str], cited_ok: list[str], cited_bad: list[str]) -> float | None:
    """Tỉ lệ dữ kiện trong câu trả lời có căn cứ trong ngữ cảnh đã đưa cho LLM.

    Dữ kiện: mỗi mức tiền, mỗi số điểm trừ (phải xuất hiện trong nội dung các điều khoản ngữ cảnh) và mỗi mã được
    trích (phải là điều khoản có trong ngữ cảnh). None nếu câu trả lời không nêu dữ kiện nào (không chấm).
    """
    ctx = du_kien("\n".join(context))
    a = du_kien(answer)
    tong = len(a) + len(cited_ok) + len(cited_bad)
    if tong == 0:
        return None
    return (len(a & ctx) + len(cited_ok)) / tong


def answer_relevance_khong_llm(answer: str, so_tien: list[int], dap_an: str, diem_tru: int | None = None) -> float:
    """Câu trả lời đáp đúng trọng tâm câu hỏi đến đâu, so với đáp án chuẩn: F1 giữa dữ kiện của câu trả lời và của
    đáp án chuẩn (mức tiền trong so_tien + số điểm trong đáp án / diem_tru).

    Câu đáp án chuẩn không có dữ kiện (vd. "chưa bị xử phạt vì quy định chưa có hiệu lực"): 1 nếu câu trả lời nói rõ
    là không/chưa áp dụng, ngược lại 0.
    """
    g = {("tien", x) for x in so_tien or []} | {("diem", x) for x in so_diem_trong(dap_an)}
    if diem_tru:
        g.add(("diem", int(diem_tru)))
    if not g:
        return 1.0 if _PHU_DINH.search(answer or "") else 0.0
    a = du_kien(answer)
    hit = len(a & g)
    if not hit:
        return 0.0
    p, r = hit / len(a), hit / len(g)
    return 2 * p * r / (p + r)
