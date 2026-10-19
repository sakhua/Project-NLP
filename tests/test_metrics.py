from graphrag.evaluation.metrics import (citation_pr, extract_amounts, f2_at_k, full_recall_at_k,
                                    key_fact_accuracy, mrr_at_k, recall_at_k)
from graphrag.retrieval.fusion import rrf

GOLD = ["A", "B"]
RET = ["C", "A", "D", "B", "E"]


def test_retrieval_metrics():
    assert recall_at_k(GOLD, RET, 2) == 0.5
    assert full_recall_at_k(GOLD, RET, 4) == 1.0
    assert full_recall_at_k(GOLD, RET, 3) == 0.0
    assert mrr_at_k(GOLD, RET, 5) == 0.5
    assert round(f2_at_k(GOLD, RET, 4), 4) == round(5 * 0.5 * 1 / (4 * 0.5 + 1), 4)


def test_amounts():
    a = extract_amounts("Phạt tiền từ 12 triệu đến 14.000.000 đồng, trừ 6 điểm; hoặc 1,5 triệu")
    assert {12_000_000, 14_000_000, 1_500_000} <= a
    assert key_fact_accuracy({12_000_000, 14_000_000}, "phạt 12.000.000 đồng đến 14 triệu đồng") == 1.0


def test_citation_and_rrf():
    assert citation_pr(["X", "Y"], ["X", "Z"]) == (0.5, 0.5)
    fused = rrf([["a", "b", "c"], ["b", "a"]], k=60)
    assert {fused[0][0], fused[1][0]} == {"a", "b"}
