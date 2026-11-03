"""Kiểm tra phần chấm điểm của scripts/chay_bo_test.py (không gọi API)."""
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


def test_cham_dung_sai():
    q = {"so_tien": [18_000_000, 20_000_000], "diem_tru": 4, "gold_ids": ["A.D6.K9.b", "A.D6.K16.b"]}
    out = {"answer": "Phạt 18.000.000–20.000.000 đồng và trừ 04 điểm [A.D6.K9.b].",
           "citations": ["A.D6.K9.b", "A.D6.K9"], "units": [{"id": "A.D6.K9.b"}, {"id": "A.D6.K16.b"}]}
    c = bt.cham(q, out)
    assert c["dung"] and c["ngu_canh_du"] and c["trich_dan_recall"] == 0.5 and c["trich_dan_precision"] == 1.0
    out["answer"] = "Phạt 18.000.000–20.000.000 đồng, trừ 6 điểm."
    assert not bt.cham(q, out)["dung"]


def test_cham_cau_chua_hieu_luc():
    q = {"so_tien": [], "diem_tru": None, "gold_ids": ["X"], "so_tien_khong_duoc_co": [800_000, 1_000_000]}
    assert bt.cham(q, {"answer": "Chưa bị xử phạt vì quy định chưa có hiệu lực.", "citations": [], "units": []})["dung"]
    assert not bt.cham(q, {"answer": "Phạt 800.000–1.000.000 đồng.", "citations": [], "units": []})["dung"]


def test_ragas_do_do_theo_ma():
    """Hai độ đo RAGAS theo mã gold không cần LLM (bỏ qua nếu chưa cài extras ragas)."""
    import pytest

    pytest.importorskip("ragas")
    from graphrag.evaluation.ragas_eval import cham_ragas

    rows = [{"cau_hoi": "Ô tô vượt đèn đỏ bị phạt bao nhiêu?", "ngay_ap_dung": "2026-10-15", "tra_loi": "18–20 triệu",
             "ngu_canh": ["A", "B"], "ngu_canh_text": ["a", "b"], "dap_an": "18–20 triệu", "gold_ids": ["A", "C"]}]
    d = cham_ragas(rows, {}, co_llm=False)[0]
    assert d["id_based_context_precision"] == 0.5 and d["id_based_context_recall"] == 0.5
