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


def test_faithfulness_va_answer_relevance_khong_llm():
    from graphrag.evaluation.metrics import answer_relevance_khong_llm as ar, faithfulness_khong_llm as fa, so_diem_trong

    ctx = ["Điều 6 – khoản 9: Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng … Không chấp hành đèn tín hiệu;",
           "Thực hiện hành vi quy định tại điểm b khoản 9 Điều này bị trừ điểm giấy phép lái xe 04 điểm;"]
    tot = "Phạt 18–20 triệu đồng [ND168_2024.D6.K9.b] và trừ 4 điểm."
    assert fa(tot, ctx, ["ND168_2024.D6.K9.b"], []) == 1.0
    bia = "Phạt 18–25 triệu đồng và trừ 6 điểm [X.D1]."           # 25 triệu, 6 điểm, mã lạ: không có căn cứ
    assert fa(bia, ctx, [], ["X.D1"]) == 1 / 4                  # 18 triệu có căn cứ; 25 triệu, 6 điểm, mã lạ thì không
    assert fa("Không rõ.", ctx, [], []) is None
    assert so_diem_trong("điểm b khoản 9, trừ 04 điểm") == {4}
    assert ar(tot, [18_000_000, 20_000_000], "Phạt 18.000.000–20.000.000 đồng, trừ 4 điểm.") == 1.0
    assert round(ar("Phạt 18 triệu đến 20 triệu, hoặc 4 triệu đến 6 triệu", [18_000_000, 20_000_000], "…"), 3) == 0.667
    assert ar("Chưa bị xử phạt vì quy định chưa có hiệu lực.", [], "Chưa bị xử phạt") == 1.0
    assert ar("Phạt 800.000 đồng.", [], "Chưa bị xử phạt") == 0.0
