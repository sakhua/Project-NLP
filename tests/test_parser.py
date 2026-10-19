"""Kiểm thử parser trên một văn bản .docx nhỏ tự tạo (không cần dữ liệu thật)."""
import pytest

docx = pytest.importorskip("docx")

from graphrag.common.ids import make_chuong_id, parse_id  # noqa: E402
from graphrag.parsing.structure_parser import parse, parse_scope  # noqa: E402


def _make(tmp_path):
    d = docx.Document()
    for t in ["NGHỊ ĐỊNH", "Căn cứ Luật ...;", "Chương I", "QUY ĐỊNH CHUNG",
              "Điều 1. Phạm vi điều chỉnh", "Nghị định này quy định:",
              "1. Phạt tiền từ 400.000 đồng đến 600.000 đồng đối với hành vi sau đây:",
              "a) Không chấp hành hiệu lệnh;", "b) Dừng xe sai quy định;", "2. Khoản hai.",
              "Điều 2. Sửa đổi, bổ sung Điều 5 Nghị định số 1/2024/NĐ-CP",
              "1. Sửa đổi, bổ sung khoản 3 như sau:",
              "“3. Nội dung mới:", "a) điểm mới a;", "Điều 9. Không phải Điều của văn bản này", "b) điểm mới b.”.",
              "2. Bãi bỏ khoản 4."]:
        d.add_paragraph(t)
    tb = d.add_table(rows=2, cols=2)
    tb.cell(0, 1).text = "Nơi nhận:"
    d.add_paragraph("PHỤ LỤC I")
    d.add_paragraph("1. Không được đưa vào corpus")
    p = tmp_path / "ND1_2024.docx"
    d.save(p)
    return p


def test_structure_quotes_and_stop(tmp_path):
    res = parse("ND1_2024", _make(tmp_path), label="Nghị định 1/2024/NĐ-CP")
    ids = [u["id"] for u in res.units]
    assert ids == ["ND1_2024.C1", "ND1_2024.D1", "ND1_2024.D1.K1", "ND1_2024.D1.K1.a", "ND1_2024.D1.K1.b",
                   "ND1_2024.D1.K2", "ND1_2024.D2", "ND1_2024.D2.K1", "ND1_2024.D2.K2"]
    u = {x["id"]: x for x in res.units}
    assert u["ND1_2024.C1"]["tieu_de"] == "QUY ĐỊNH CHUNG"
    assert u["ND1_2024.D1"]["parent_id"] == "ND1_2024.C1"
    assert u["ND1_2024.D1.K1.a"]["noi_dung"] == "Không chấp hành hiệu lệnh;"
    assert "Phạt tiền từ 400.000" in u["ND1_2024.D1.K1.a"]["ngu_canh"]
    k = u["ND1_2024.D2.K1"]                        # nội dung trong ngoặc kép gắn vào câu lệnh sửa đổi
    assert k["co_trich_dan"] and "Điều 9." in k["noi_dung"] and "điểm mới b" in k["noi_dung"]
    assert not res.warnings


def test_scope(tmp_path):
    res = parse("ND1_2024", _make(tmp_path), scope=parse_scope("dieu:2"))
    assert {u["id"] for u in res.units if u["cap"] != "Chuong"} == {"ND1_2024.D2", "ND1_2024.D2.K1", "ND1_2024.D2.K2"}


def test_chuong_id():
    assert make_chuong_id("ND168_2024", "IV") == "ND168_2024.C4"
    assert parse_id("ND168_2024.C4").level == "Chuong"
