"""Dựng phiên bản hiệu lực (graphrag/parsing/versioning.py) trên ví dụ thật NĐ 168 ← NĐ 238."""
from datetime import date

from graphrag.parsing.versioning import DocInfo, build_versions, valid_at

DIEU6 = "Nghị định 168/2024/NĐ-CP, Điều 6. Xử phạt người điều khiển xe ô tô"
UNITS = [
    {"id": "ND168_2024.D6", "van_ban_id": "ND168_2024", "cap": "Dieu", "parent_id": "ND168_2024.C2", "so": "6",
     "thu_tu": 78, "tieu_de": "Xử phạt người điều khiển xe ô tô", "noi_dung": "Điều 6. Xử phạt người điều khiển xe ô tô",
     "ngu_canh": DIEU6, "chuong": "ND168_2024.C2", "muc": None, "co_trich_dan": False},
    {"id": "ND168_2024.D6.K1", "van_ban_id": "ND168_2024", "cap": "Khoan", "parent_id": "ND168_2024.D6", "so": "1",
     "thu_tu": 79, "tieu_de": None, "noi_dung": "Phạt tiền từ 400.000 đồng đến 600.000 đồng …",
     "ngu_canh": DIEU6, "chuong": "ND168_2024.C2", "muc": None, "co_trich_dan": False},
    {"id": "ND168_2024.D6.K3", "van_ban_id": "ND168_2024", "cap": "Khoan", "parent_id": "ND168_2024.D6", "so": "3",
     "thu_tu": 91, "tieu_de": None, "noi_dung": "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng …",
     "ngu_canh": DIEU6, "chuong": "ND168_2024.C2", "muc": None, "co_trich_dan": False},
    {"id": "ND168_2024.D6.K3.m", "van_ban_id": "ND168_2024", "cap": "Diem", "parent_id": "ND168_2024.D6.K3",
     "so": "m", "thu_tu": 103, "tieu_de": None,
     "noi_dung": "Chở trẻ em … ngồi cùng hàng ghế với người lái xe … hoặc không sử dụng thiết bị an toàn …;",
     "ngu_canh": DIEU6 + " – khoản 3: Phạt tiền …", "chuong": "ND168_2024.C2", "muc": None, "co_trich_dan": False},
    {"id": "ND168_2024.D6.K5.p", "van_ban_id": "ND168_2024", "cap": "Diem", "parent_id": "ND168_2024.D6.K5",
     "so": "p", "thu_tu": 140, "tieu_de": None, "noi_dung": "Chở người trên nóc xe; để người đu bám ở cửa xe;",
     "ngu_canh": DIEU6, "chuong": "ND168_2024.C2", "muc": None, "co_trich_dan": False},
]
MANIFEST = {
    "ND168_2024": DocInfo(date(2025, 1, 1), {"ND168_2024.D6.K3.m": date(2026, 1, 1)}),
    "ND238_2026": DocInfo(date(2026, 8, 15), {"ND168_2024.D6.K5": date(2028, 1, 1)}),
}
OPS = [
    {"nguon": "ND238_2026.D2.K1", "dich": "ND168_2024.D6.K1a", "loai": "BO_SUNG",
     "vi_tri": {"truoc": "ND168_2024.D6.K1"}, "noi_dung_moi": "Phạt cảnh cáo … không sử dụng thiết bị an toàn …"},
    {"nguon": "ND238_2026.D2.K2", "dich": "ND168_2024.D6.K3.m", "loai": "SUA_DOI", "pham_vi": "toan_bo",
     "noi_dung_moi": "Chở trẻ em … ngồi cùng hàng ghế với người lái xe (trừ xe ô tô chỉ có một hàng ghế);"},
    {"nguon": "ND238_2026.D19.K10", "dich": "ND168_2024.D6.K5.p", "loai": "SUA_DOI", "pham_vi": "cum_tu",
     "cum_tu_cu": "Chở người trên nóc xe; để người đu bám ở cửa xe", "cum_tu_moi": "Để người nằm, ngồi, đu bám bên ngoài xe"},
    {"nguon": "ND238_2026.D19.K17", "dich": "ND168_2024.D6.K3", "loai": "BAI_BO"},
]


def _build():
    rows, warnings = build_versions(UNITS, OPS, MANIFEST)
    return rows, warnings


def test_original_uses_exception_date():
    rows, _ = _build()
    assert valid_at(rows, "ND168_2024.D6.K3.m", date(2025, 10, 1)) is None          # chưa có hiệu lực
    assert valid_at(rows, "ND168_2024.D6.K3.m", date(2026, 3, 1))["loai_phien_ban"] == "goc"


def test_amendment_creates_new_version_same_id():
    rows, _ = _build()
    v = [r for r in rows if r["id"] == "ND168_2024.D6.K3.m"]
    assert [r["vid"] for r in v] == ["ND168_2024.D6.K3.m@2026-01-01", "ND168_2024.D6.K3.m@2026-08-15"]
    assert v[0]["hieu_luc_den"] == "2026-08-15"
    assert v[1]["nguon_sua_doi"] == "ND238_2026.D2.K2" and "thiết bị an toàn" not in v[1]["noi_dung"]


def test_inserted_unit_and_context():
    rows, _ = _build()
    k1a = valid_at(rows, "ND168_2024.D6.K1a", date(2026, 9, 1))
    assert k1a["loai_phien_ban"] == "bo_sung" and k1a["parent_id"] == "ND168_2024.D6"
    assert k1a["thu_tu"] < 79 and k1a["ngu_canh"].startswith("Nghị định 168/2024/NĐ-CP, Điều 6")
    assert valid_at(rows, "ND168_2024.D6.K1a", date(2026, 8, 14)) is None


def test_phrase_edit_uses_target_exception_date():
    rows, _ = _build()
    # ngoại lệ trong dòng ND238 cho mã cha ND168_2024.D6.K5 → thao tác lên điểm p có hiệu lực 2028
    assert "nóc xe" in valid_at(rows, "ND168_2024.D6.K5.p", date(2027, 6, 1))["noi_dung"]
    assert valid_at(rows, "ND168_2024.D6.K5.p", date(2028, 1, 1))["noi_dung"].startswith("Để người nằm")


def test_repeal_closes_children():
    rows, _ = _build()
    assert valid_at(rows, "ND168_2024.D6.K3", date(2026, 9, 1)) is None
    assert valid_at(rows, "ND168_2024.D6.K3.m", date(2026, 9, 1)) is None


def test_missing_phrase_is_warning():
    op = {"nguon": "ND238_2026.D19.K1", "dich": "ND168_2024.D6.K1", "loai": "SUA_DOI", "pham_vi": "cum_tu",
          "cum_tu_cu": "không có trong văn bản", "cum_tu_moi": "x"}
    rows, warnings = build_versions(UNITS, [op], MANIFEST)
    assert any("không thấy cụm từ" in w for w in warnings)
    assert len([r for r in rows if r["id"] == "ND168_2024.D6.K1"]) == 1
