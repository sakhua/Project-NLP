"""Kiểm tra phần chấm điểm của scripts/chay_bo_test.py (6 độ đo không dùng LLM, không gọi API)."""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[1] / "scripts" / "chay_bo_test.py"
_spec = importlib.util.spec_from_file_location("chay_bo_test", _p)
bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bt)


def test_so_tien_nhieu_cach_viet():
    assert {18_000_000, 20_000_000} <= bt.so_tien_trong("Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng")
    assert {18_000_000, 20_000_000} <= bt.so_tien_trong("phạt từ 18 đến 20 triệu đồng")
    assert {800_000, 1_000_000} <= bt.so_tien_trong("800.000–1.000.000 đồng")
    assert 1_500_000 in bt.so_tien_trong("khoảng 1,5 triệu đồng")
    assert 500_000 in bt.so_tien_trong("500 nghìn đồng")


def test_cham_sau_do_do():
    q = {"so_tien": [18_000_000, 20_000_000], "diem_tru": 4, "gold_ids": ["A.D6.K9.b", "A.D6.K16.b"],
         "dap_an": "Phạt 18.000.000–20.000.000 đồng và trừ 4 điểm."}
    r = {"truy_hoi": ["A.D6.K9.b"] + [f"X{i}" for i in range(10)] + ["A.D6.K16.b"],
         "tra_loi": "Phạt 18.000.000–20.000.000 đồng và trừ 04 điểm [A.D6.K9.b].",
         "ngu_canh_text": ["khoản 9: Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng",
                           "… bị trừ điểm giấy phép lái xe 04 điểm"], "trich_dan": ["A.D6.K9.b"], "trich_dan_la": []}
    c = bt.cham(q, r)
    assert c["recall@10"] == 0.5 and c["full_recall@10"] == 0 and c["full_recall@40"] == 1   # khoản trừ điểm ở hạng 12
    assert c["mrr@10"] == 1.0 and c["faithfulness"] == 1.0 and c["answer_relevance"] == 1.0
    assert c["gold_thieu"] == []
    r["tra_loi"] = "Phạt 18.000.000–20.000.000 đồng, trừ 6 điểm."                           # sai số điểm
    c = bt.cham(q, r)
    assert c["faithfulness"] == 3 / 4 and round(c["answer_relevance"], 3) == 0.667   # 6 điểm không có căn cứ


def test_cau_chua_hieu_luc():
    q = {"so_tien": [], "diem_tru": None, "gold_ids": ["X"], "dap_an": "Chưa bị xử phạt theo quy định này."}
    r = {"truy_hoi": ["X"], "tra_loi": "Chưa bị xử phạt vì quy định chưa có hiệu lực [X].", "ngu_canh_text": ["…"],
         "trich_dan": ["X"], "trich_dan_la": []}
    assert bt.cham(q, r)["answer_relevance"] == 1.0
    r["tra_loi"] = "Phạt 800.000–1.000.000 đồng."
    c = bt.cham(q, r)
    assert c["answer_relevance"] == 0.0 and c["faithfulness"] == 1 / 3          # 2 mức tiền không có căn cứ, mã X có


def test_bootstrap():
    d, p = bt.bootstrap([1.0] * 30 + [0.0] * 10, [0.0] * 30 + [0.0] * 10)
    assert d == 0.75 and p < 0.05
    assert bt.bootstrap([1.0, 0.0], [1.0, 0.0]) == (0.0, 1.0)
