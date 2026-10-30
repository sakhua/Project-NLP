"""Phân tích câu lệnh sửa đổi và dẫn chiếu, trên câu chữ lấy từ NĐ 238/2026 và NĐ 168/2024."""
from graphrag.parsing.amendment_parser import parse_all
from graphrag.parsing.legal_refs import parse_targets
from graphrag.parsing.reference_extractor import find_references


def U(uid, cap, parent, so, noi_dung, tieu_de=None, quoted=False):
    return {"id": uid, "van_ban_id": uid.split(".")[0], "cap": cap, "parent_id": parent, "so": so, "thu_tu": 0,
            "tieu_de": tieu_de, "noi_dung": noi_dung, "ngu_canh": "", "co_trich_dan": quoted}


T = "ND168_2024"
A = "ND238_2026"
TARGET = [
    U(f"{T}.D6", "Dieu", T, "6", "Điều 6. Xử phạt người điều khiển xe ô tô", "Xử phạt người điều khiển xe ô tô"),
    U(f"{T}.D6.K1", "Khoan", f"{T}.D6", "1", "Phạt tiền từ 400.000 đồng đến 600.000 đồng …"),
    U(f"{T}.D6.K3", "Khoan", f"{T}.D6", "3", "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng …"),
    U(f"{T}.D6.K3.m", "Diem", f"{T}.D6.K3", "m", "Chở trẻ em … hoặc không sử dụng thiết bị an toàn …;"),
    U(f"{T}.D13.K8.b", "Diem", f"{T}.D13.K8", "b", "Điều khiển xe không gắn đủ biển số …"),
    U(f"{T}.D21.K5.c", "Diem", f"{T}.D21.K5", "c", "Điều khiển xe ô tô kinh doanh vận tải … (bản cũ)"),
    U(f"{T}.D32.K17.d", "Diem", f"{T}.D32.K17", "d", "Tái phạm …"),
    U(f"{T}.D32.K17.đ", "Diem", f"{T}.D32.K17", "đ", "Tái phạm …"),
    U(f"{T}.D42", "Dieu", T, "42", "Điều 42. Thẩm quyền xử phạt", "Thẩm quyền xử phạt"),
    U(f"{T}.D42.K1", "Khoan", f"{T}.D42", "1", "Chủ tịch Ủy ban nhân dân cấp xã có quyền:"),
    U(f"{T}.D42.K3", "Khoan", f"{T}.D42", "3", "Chủ tịch Ủy ban nhân dân cấp huyện có quyền:"),
]
AMEND = [
    U(f"{A}.D2", "Dieu", A, "2", "Điều 2. Sửa đổi, bổ sung một số điểm, khoản của Điều 6",
      "Sửa đổi, bổ sung một số điểm, khoản của Điều 6"),
    U(f"{A}.D2.K1", "Khoan", f"{A}.D2", "1", 'Bổ sung khoản 1a vào trước khoản 1 như sau:\n"1a. Phạt cảnh cáo …".', quoted=True),
    U(f"{A}.D2.K2", "Khoan", f"{A}.D2", "2",
      'Sửa đổi, bổ sung điểm m khoản 3 như sau:\n"m) Chở trẻ em … (trừ xe ô tô chỉ có một hàng ghế);".', quoted=True),
    U(f"{A}.D3", "Dieu", A, "3", '"b) Điều khiển xe không gắn đủ biển số (bản mới)".',
      "Sửa đổi, bổ sung điểm b khoản 8 Điều 13", quoted=True),
    U(f"{A}.D8", "Dieu", A, "8", "Điều 8. Sửa đổi, bổ sung một số điểm, khoản của Điều 21",
      "Sửa đổi, bổ sung một số điểm, khoản của Điều 21"),
    U(f"{A}.D8.K3", "Khoan", f"{A}.D8", "3", "Sửa đổi, bổ sung điểm c khoản 5 như sau:"),
    U(f"{A}.D8.K3.c", "Diem", f"{A}.D8.K3", "c", 'Điều khiển xe ô tô kinh doanh vận tải … (bản mới);".'),
    U(f"{A}.D13", "Dieu", A, "13", '"Điều 42. Thẩm quyền xử phạt (mới)\n1. Chủ tịch cấp xã có quyền:\na) Phạt cảnh cáo;".',
      "Sửa đổi, bổ sung Điều 42", quoted=True),
    U(f"{A}.D19", "Dieu", A, "19", "Điều 19. Bổ sung, thay thế, bãi bỏ", "Bổ sung, thay thế, bãi bỏ một số cụm từ"),
    U(f"{A}.D19.K10", "Khoan", f"{A}.D19", "10",
      'Thay thế cụm từ "thiết bị an toàn" bằng cụm từ "thiết bị an toàn phù hợp" tại điểm m khoản 3 Điều 6.'),
    U(f"{A}.D19.K17", "Khoan", f"{A}.D19", "17", "Bãi bỏ điểm d, điểm đ khoản 17 Điều 32."),
]


def _ops():
    ops, warnings = parse_all(TARGET + AMEND, [(A, T)])
    return {(o["nguon"], o["dich"], o["loai"]): o for o in ops}, warnings


def test_insert_and_amend_point():
    ops, _ = _ops()
    k1a = ops[(f"{A}.D2.K1", f"{T}.D6.K1a", "BO_SUNG")]
    assert k1a["vi_tri"] == {"truoc": f"{T}.D6.K1"} and k1a["noi_dung_moi"].startswith("Phạt cảnh cáo")
    m = ops[(f"{A}.D2.K2", f"{T}.D6.K3.m", "SUA_DOI")]
    assert m["noi_dung_moi"].endswith("một hàng ghế);")         # đã bỏ ngoặc kép ở cuối


def test_instruction_in_article_title_and_unquoted_content():
    ops, _ = _ops()
    assert (f"{A}.D3", f"{T}.D13.K8.b", "SUA_DOI") in ops
    c = ops[(f"{A}.D8.K3", f"{T}.D21.K5.c", "SUA_DOI")]          # nội dung bị tách thành điểm con (thiếu ngoặc)
    assert "(bản mới)" in c["noi_dung_moi"]


def test_replace_whole_article_repeals_missing_clauses():
    ops, _ = _ops()
    assert (f"{A}.D13", f"{T}.D42", "THAY_THE") in ops
    assert (f"{A}.D13", f"{T}.D42.K3", "BAI_BO") in ops               # khoản 3 không còn trong Điều 42 mới
    assert (f"{A}.D13", f"{T}.D42.K1.a", "BO_SUNG") in ops


def test_phrase_and_repeal():
    ops, _ = _ops()
    p = ops[(f"{A}.D19.K10", f"{T}.D6.K3.m", "SUA_DOI")]
    assert p["pham_vi"] == "cum_tu" and p["cum_tu_moi"] == "thiết bị an toàn phù hợp"
    assert (f"{A}.D19.K17", f"{T}.D32.K17.d", "BAI_BO") in ops and (f"{A}.D19.K17", f"{T}.D32.K17.đ", "BAI_BO") in ops


def test_target_lists():
    refs = parse_targets("khoản 7 Điều 11, khoản 3 Điều 12, Điều 18, khoản 1, 3 và 6 Điều 25")
    assert [(r.dieu, r.khoan, r.diem) for r in refs] == [
        ("11", "7", None), ("12", "3", None), ("18", None, None), ("25", "1", None), ("25", "3", None), ("25", "6", None)]
    refs = parse_targets("Điều 13 (điểm a khoản 4; điểm a, điểm b khoản 7), Điều 14 (điểm c khoản 2)")
    assert [(r.dieu, r.khoan, r.diem) for r in refs] == [
        ("13", "4", "a"), ("13", "7", "a"), ("13", "7", "b"), ("14", "2", "c")]


def test_references():
    text = "Thực hiện hành vi quy định tại điểm h khoản 5; khoản 6; điểm b, điểm c khoản 9 Điều này bị trừ 04 điểm"
    dst = [e["dst"] for e in find_references(text, "ND168_2024.D6.K16.b")]
    assert dst == ["ND168_2024.D6.K5.h", "ND168_2024.D6.K6", "ND168_2024.D6.K9.b", "ND168_2024.D6.K9.c"]
    e = find_references("theo quy định tại khoản 2 Điều 10 của Luật Trật tự, an toàn giao thông đường bộ",
                        "ND168_2024.D6.K1")
    assert e[0]["dst"] == "L36_2024.D10.K2"
    e = find_references("theo quy định tại khoản 1 Điều 46 của Luật Xử lý vi phạm hành chính", "ND168_2024.D6.K1")
    assert e[0]["ngoai_pham_vi"] and e[0]["dst"] is None
