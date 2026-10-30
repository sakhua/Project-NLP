from graphrag.pipeline.prompts import build_user, format_context, parse_citations, ten_dieu_khoan

UNIT = {
    "vid": "ND168_2024.D6.K3.m@2026-08-15", "id": "ND168_2024.D6.K3.m",
    "noi_dung": "Chở trẻ em dưới 10 tuổi … (trừ xe ô tô chỉ có một hàng ghế);",
    "ngu_canh": "Nghị định 168/2024/NĐ-CP, Điều 6. Xử phạt … – khoản 3: Phạt tiền từ 800.000 đồng đến 1.000.000 đồng …",
    "hieu_luc_tu": "2026-08-15", "hieu_luc_den": None, "nguon_sua_doi": "ND238_2026.D2.K2",
}


def test_ten_dieu_khoan():
    assert ten_dieu_khoan("ND168_2024.D6.K3.m", "Nghị định 168/2024/NĐ-CP") == \
        "điểm m khoản 3 Điều 6 Nghị định 168/2024/NĐ-CP"
    assert ten_dieu_khoan("ND168_2024.D6.K3.m@2026-08-15").startswith("điểm m khoản 3 Điều 6")


def test_context_has_lead_sentence_and_amendment_note():
    ctx = format_context([UNIT])
    assert ctx.startswith("[ND168_2024.D6.K3.m] điểm m khoản 3 Điều 6 Nghị định 168/2024/NĐ-CP")
    assert "800.000 đồng" in ctx                      # mức phạt nằm ở câu dẫn của khoản
    assert "hiệu lực từ 15/08/2026" in ctx and "khoản 2 Điều 2 Nghị định 238/2026 sửa đổi" in ctx
    user = build_user("Chở cháu 8 tuổi ngồi ghế trước bị phạt thế nào?", "2026-09-01", [UNIT])
    assert "NGÀY ÁP DỤNG: 01/09/2026" in user and "NGỮ CẢNH (1 điều khoản)" in user


def test_parse_citations():
    ans = ("Phạt 800.000 – 1.000.000 đồng [ND168_2024.D6.K3.m]. Trừ điểm [ND168_2024.D6.K16.b][ND168_2024.D6.K3.m]; "
           "xem thêm [ND168_2024.D6.K1a, ND999_2024.D1] và [điểm a].")
    ok, la = parse_citations(ans, allowed=["ND168_2024.D6.K3.m@2026-08-15", "ND168_2024.D6.K1a"])
    assert ok == ["ND168_2024.D6.K3.m", "ND168_2024.D6.K1a"]
    assert la == ["ND168_2024.D6.K16.b", "ND999_2024.D1"]
    ok, la = parse_citations("[ND168_2024.D41.K4.k1]")
    assert ok == ["ND168_2024.D41.K4.k1"] and la == []
