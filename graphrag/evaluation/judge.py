"""LLM-as-a-judge chấm Đúng / Một phần / Sai; đo độ tin cậy bằng Cohen's kappa.

Phụ trách: TV3.
"""
from __future__ import annotations

JUDGE_PROMPT = """Bạn là giám khảo. So sánh CÂU TRẢ LỜI với ĐÁP ÁN CHUẨN cho câu hỏi pháp luật.
Chỉ trả về một trong ba nhãn: DUNG, MOT_PHAN, SAI.

CÂU HỎI: {question}
ĐÁP ÁN CHUẨN: {gold}
CÂU TRẢ LỜI: {answer}
NHÃN:"""


def judge(question: str, gold: str, answer: str) -> str:
    # TODO(TV3): get_llm(cfg, role="judge") (evaluation.judge_model, khác mô hình sinh câu trả lời),
    # cache kết quả vào data/processed/cache/
    raise NotImplementedError


def kappa(human: list[str], llm: list[str]) -> float:
    from sklearn.metrics import cohen_kappa_score

    return float(cohen_kappa_score(human, llm))
