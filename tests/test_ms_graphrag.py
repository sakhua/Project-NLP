"""Kiểm thử baseline GraphRAG kiểu Microsoft không cần DB/mạng: LLM, PostgreSQL giả."""
import json
import re
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from graphrag.common.config import load_config
from graphrag.ms_graphrag import indexing as ix
from graphrag.pipeline import he_thong, ms_graphrag

D = date.fromisoformat


class FakeIndexLLM:
    """Trả JSON tùy theo loại prompt: trích xuất / tóm tắt / báo cáo cộng đồng."""

    def __init__(self):
        self.n = {"trich": 0, "tom_tat": 0, "bao_cao": 0}

    def generate(self, system, user):
        if "xây dựng đồ thị tri thức" in system:
            self.n["trich"] += 1
            text = user.split("ĐOẠN VĂN BẢN:")[1].split("KẾT QUẢ")[0].strip()
            xe = "xe ô tô" if "xe ô tô" in text else "xe mô tô"
            m = re.search(r"Phạt tiền từ ([\d.]+) đồng đến ([\d.]+) đồng", text)
            hv = text.split("\n")[-1].strip(" ;.").lower()[:60]
            tt = [{"ten": xe, "loai": "PHUONG_TIEN", "mo_ta": f"Phương tiện {xe}"},
                  {"ten": hv, "loai": "HANH_VI", "mo_ta": f"Hành vi {hv}"}]
            qh = [{"nguon": hv, "dich": xe, "mo_ta": "hành vi của người lái", "do_manh": 7}]
            if m:
                ct = f"phạt tiền từ {m.group(1)} đồng đến {m.group(2)} đồng"
                tt.append({"ten": ct, "loai": "CHE_TAI", "mo_ta": "Mức phạt"})
                qh.append({"nguon": hv, "dich": ct, "mo_ta": "bị phạt", "do_manh": 9})
            qh.append({"nguon": hv, "dich": "không có", "mo_ta": "bị bỏ vì không có thực thể", "do_manh": 3})
            return "```json\n" + json.dumps({"thuc_the": tt, "quan_he": qh}, ensure_ascii=False) + "\n```"
        if "tổng hợp thông tin" in system:
            self.n["tom_tat"] += 1
            return "Mô tả tổng hợp."
        if "CỘNG ĐỒNG" in system:
            self.n["bao_cao"] += 1
            return json.dumps({"tieu_de": "Nhóm vi phạm", "tom_tat": "Tóm tắt nhóm", "muc_do": 7,
                               "phat_hien": [{"tom_tat": "ý", "giai_thich": "giải thích"}]}, ensure_ascii=False)
        raise AssertionError(system[:50])


def _versions():
    out = []
    for i, (xe, tien) in enumerate([("ô tô", "18.000.000"), ("ô tô", "4.000.000"), ("mô tô", "800.000")] * 4):
        out.append({"vid": f"ND168_2024.D6.K{i}.a@2025-01-01", "id": f"ND168_2024.D6.K{i}.a", "van_ban_id": "ND168_2024",
                    "cap": "Diem", "ngu_canh": f"Điều 6 xe {xe} – khoản {i}: Phạt tiền từ {tien} đồng đến 20.000.000 đồng",
                    "noi_dung": f"Hành vi số {i % 3} khi điều khiển xe {xe};\n"})
    out.append({"vid": "X.C1@2025-01-01", "id": "X.C1", "van_ban_id": "X", "cap": "Chuong", "ngu_canh": "", "noi_dung": "CHƯƠNG I"})
    out.append({"vid": "Y@2026-08-15", "id": "Y", "van_ban_id": "ND238_2026", "cap": "Khoan", "ngu_canh": "",
                "noi_dung": "Sửa đổi, bổ sung điểm m khoản 3 Điều 6 như sau: …"})
    return out


def test_indexing_end_to_end(tmp_path):
    llm = FakeIndexLLM()
    units = ix.don_vi_van_ban(_versions())
    assert len(units) == 12                                     # bỏ chương và câu lệnh sửa đổi
    cache = ix.Cache(tmp_path / "c.jsonl")
    kq, loi = ix.trich_xuat(llm, units, cache, workers=4)
    assert not loi and len(kq) == 12 and llm.n["trich"] == 12
    kq2, _ = ix.trich_xuat(llm, units, ix.Cache(tmp_path / "c.jsonl"), workers=4)   # chạy lại: dùng lưu đệm
    assert llm.n["trich"] == 12 and kq2 == kq
    tt, qh = ix.gop(kq, {u["vid"]: u["id"] for u in units})
    assert "xe ô tô" in tt and tt["xe ô tô"]["tan_suat"] == 8 and tt["xe ô tô"]["loai"] == "PHUONG_TIEN"
    assert all("không có" not in k for k in qh)                 # quan hệ tới thực thể không tồn tại bị bỏ
    ix.tom_tat_mo_ta(llm, tt, qh, ix.Cache(tmp_path / "t.jsonl"), nguong_ky_tu=10)
    assert all("mo_ta_tong" in d for d in list(tt.values()) + list(qh.values()))
    comms, algo = ix.cong_dong(tt, qh, max_cluster_size=3)
    assert comms and algo in ("leiden", "louvain") and all(len(c["thanh_vien"]) >= 2 for c in comms)
    assert {c["cap"] for c in comms} >= {0}
    loi = ix.bao_cao_cong_dong(llm, comms, tt, qh, ix.Cache(tmp_path / "b.jsonl"))
    assert not loi and all(c["bao_cao"]["tieu_de"] for c in comms)
    ix.luu_ket_qua(tmp_path, tt, qh, comms, algo)
    rows = ix.doc_jsonl(tmp_path / "cong_dong.jsonl")
    assert rows[0]["bao_cao"].startswith("# Nhóm vi phạm")
    e = ix.doc_jsonl(tmp_path / "thuc_the.jsonl")[0]
    assert {"id", "ten", "loai", "mo_ta", "vids", "don_vi", "bac"} <= set(e)


def test_doc_json_and_chuan_hoa():
    assert ix.doc_json('Kết quả: {"a": [1, 2,], }') == {"a": [1, 2]}
    assert ix.doc_json("không có json") is None
    assert ix.chuan_hoa("  Xe  Ô TÔ. ") == "xe ô tô"


# ---------------- truy vấn ----------------
class FakeLLM:
    def __init__(self):
        self.calls = []

    def generate(self, system, user):
        self.calls.append((system, user))
        if "Map" in system or "liệt kê các ý" in system:
            return '{"y": [{"mo_ta": "Ô tô vượt đèn đỏ phạt 18–20 triệu [CĐ 0-1]", "diem": 90}]}'
        if "tổng quan" in system:
            return "Tổng hợp: ô tô vượt đèn đỏ bị phạt nặng [CĐ 0-1]."
        return "Phạt 18.000.000 – 20.000.000 đồng [ND168_2024.D6.K9.b]."

    def generate_stream(self, system, user):
        for w in self.generate(system, user).split(" "):
            yield w + " "


class FakePool:
    def connection(self):
        class C:
            def __enter__(s):
                return SimpleNamespace(rollback=lambda: None)

            def __exit__(s, *a):
                return False
        return C()


def _unit(uid, tu="2025-01-01", den=None):
    return {"vid": f"{uid}@{tu}", "id": uid, "van_ban_id": "ND168_2024", "cap": "Diem", "tieu_de": None,
            "noi_dung": "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;", "ngu_canh": "Điều 6 – khoản 9",
            "hieu_luc_tu": D(tu), "hieu_luc_den": D(den) if den else None, "nguon_sua_doi": None, "loai_phien_ban": "goc"}


@pytest.fixture
def res(monkeypatch):
    s = ms_graphrag.ms_store
    monkeypatch.setattr(s, "dem", lambda conn: {"ms_thuc_the": 3})
    monkeypatch.setattr(s, "tim_thuc_the", lambda conn, q, k=10: [
        {"id": "vượt đèn đỏ", "ten": "vượt đèn đỏ", "loai": "HANH_VI", "mo_ta": "không chấp hành đèn", "bac": 3, "diem": .9},
        {"id": "xe ô tô", "ten": "xe ô tô", "loai": "PHUONG_TIEN", "mo_ta": "ô tô", "bac": 9, "diem": .8}])
    monkeypatch.setattr(s, "quan_he_cua", lambda conn, ids, limit=200: [
        {"nguon": "vượt đèn đỏ", "dich": "phạt 18-20 triệu", "mo_ta": "bị phạt", "trong_so": 9, "tan_suat": 2},
        {"nguon": "vượt đèn đỏ", "dich": "xe ô tô", "mo_ta": "của ô tô", "trong_so": 7, "tan_suat": 1}])
    monkeypatch.setattr(s, "lay_thuc_the", lambda conn, ids: [
        {"id": "phạt 18-20 triệu", "ten": "phạt 18-20 triệu", "loai": "CHE_TAI", "mo_ta": "mức phạt", "bac": 2}])
    monkeypatch.setattr(s, "cong_dong_cua", lambda conn, ids, limit=3: [
        {"id": "0-1", "cap": 0, "tieu_de": "Vi phạm đèn tín hiệu", "tom_tat": "…", "bao_cao": "# …", "muc_do": 8,
         "so_thanh_vien": 5, "so_khop": 2}])
    monkeypatch.setattr(s, "don_vi_cua", lambda conn, ids: [
        {"thuc_the_id": "vượt đèn đỏ", "vid": "ND168_2024.D6.K9.b@2025-01-01", "don_vi_id": "ND168_2024.D6.K9.b"},
        {"thuc_the_id": "phạt 18-20 triệu", "vid": "ND168_2024.D6.K9@2025-01-01", "don_vi_id": "ND168_2024.D6.K9"},
        {"thuc_the_id": "xe ô tô", "vid": "ND168_2024.D6.K3.m@2026-01-01", "don_vi_id": "ND168_2024.D6.K3.m"}])
    monkeypatch.setattr(s, "cong_dong_cho_global", lambda conn, q, cap=0, k=24: [
        {"id": f"0-{i}", "cap": 0, "tieu_de": f"CĐ {i}", "tom_tat": "…", "bao_cao": "# báo cáo", "muc_do": 7,
         "so_thanh_vien": 4, "gan": .5} for i in range(8)])
    units = [_unit("ND168_2024.D6.K9.b"), _unit("ND168_2024.D6.K9"), _unit("ND168_2024.D6.K3.m", tu="2026-01-01")]
    pg = ms_graphrag.postgres
    monkeypatch.setattr(pg, "fetch_valid", lambda conn, ids, ngay: [
        u for u in units if u["id"] in ids and u["hieu_luc_tu"] <= ngay])
    monkeypatch.setattr(pg, "get_units", lambda conn, ids: [u for u in units if u["id"] in ids])
    monkeypatch.setattr(pg, "latest_versions", lambda conn, ids: {u["id"]: u for u in units if u["id"] in ids})
    emb = SimpleNamespace(encode_queries=lambda t: np.zeros((1, 4)))
    bm25 = SimpleNamespace(search=lambda *a, **k: pytest.fail("B2 không được dùng BM25"))
    return SimpleNamespace(cfg=load_config("local"), embedder=emb, llm=FakeLLM(), pg_pool=FakePool(), bm25=bm25)


def test_local_search(res):
    out = ms_graphrag.answer(res, "Ô tô vượt đèn đỏ bị phạt bao nhiêu?", ngay=D("2025-10-01"))
    assert [s["key"] for s in out["steps"]] == ["intent", "entities", "expand", "community", "units", "context", "generate"]
    ids = [u["id"] for u in out["units"]]
    assert ids == ["ND168_2024.D6.K9.b", "ND168_2024.D6.K9"]            # K3.m chưa có hiệu lực ngày 01/10/2025
    assert out["notes"] and out["notes"][0]["id"] == "ND168_2024.D6.K3.m"
    assert out["citations"] == ["ND168_2024.D6.K9.b"] and out["units"][0]["origin"] == "entity"
    user = res.llm.calls[-1][1]
    assert "THÔNG TIN TỪ ĐỒ THỊ THỰC THỂ" in user and "Vi phạm đèn tín hiệu" in user and "phạt 18-20 triệu" in user
    roles = {n["role"] for n in out["graph"]["nodes"]}
    assert {"entity", "entity_nb", "seed"} <= roles
    assert {e["type"] for e in out["graph"]["edges"]} == {"LIEN_QUAN", "XUAT_HIEN_TAI"}
    ct = {x["key"]: x.get("chi_tiet") for x in out["steps"]}
    assert all(ct[k] and ct[k]["thuat_toan"] for k in ("entities", "expand", "community", "units", "context", "generate"))
    assert [d["id"] for d in ct["units"]["bang"][0]["dong"] if d["kieu"] == "giu"] == ids
    # tắt lọc theo ngày: "GraphRAG nguyên bản" lấy cả điều khoản chưa có hiệu lực
    raw = ms_graphrag.answer(res, "Ô tô vượt đèn đỏ bị phạt bao nhiêu?", ngay=D("2025-10-01"), use_temporal_filter=False)
    assert "ND168_2024.D6.K3.m" in [u["id"] for u in raw["units"]]


def test_global_search_stream(res):
    evs = list(ms_graphrag.run(res, "Tổng quan các quy định về nồng độ cồn?", che_do="global", stream=True))
    done = evs[-1]
    assert done["type"] == "done" and done["che_do"] == "global" and "Tổng hợp" in done["answer"]
    assert [s["key"] for s in done["steps"]] == ["intent", "communities", "map", "reduce"]
    assert len(done["graph_context"]["cong_dong"]) == 8 and done["citations"] == []
    maps = [c for c in res.llm.calls if "liệt kê các ý" in c[0]]
    assert len(maps) == 2                                               # 8 báo cáo, 6 báo cáo mỗi lượt map


def test_no_index_message(res, monkeypatch):
    monkeypatch.setattr(ms_graphrag.ms_store, "dem", lambda conn: {"ms_thuc_the": 0})
    out = ms_graphrag.answer(res, "Ô tô vượt đèn đỏ bị phạt bao nhiêu?")
    assert "Chưa có chỉ mục GraphRAG" in out["answer"]


def test_dispatcher(res):
    out = he_thong.answer(res, "Xin chào", he_thong="ms_graphrag")
    assert out["he_thong"] == "ms_graphrag" and out["intent"] == "chao"
    with pytest.raises(ValueError):
        he_thong.answer(res, "x", he_thong="khong_co")


def test_stop_on_account_error(tmp_path):
    class HetHanMuc:
        def __init__(self):
            self.n = 0

        def generate(self, s, u):
            self.n += 1
            raise RuntimeError('/chat/completions lỗi 403: {"error":{"message":"Key limit exceeded (total limit)."}}')
    llm = HetHanMuc()
    with pytest.raises(ix.LoiKhongTheTiepTuc):
        ix.trich_xuat(llm, ix.don_vi_van_ban(_versions()), ix.Cache(tmp_path / "c.jsonl"), workers=1)
    assert llm.n == 1                                                  # dừng ngay, không gọi tiếp 11 đơn vị còn lại


def test_loc_trung_va_lay_mau():
    ds = ["Mức phạt tiền tại khoản 3 Điều 6 Nghị định 168/2024.", "Mức phạt tiền tại khoản 3 Điều 6 Nghị định 168/2024",
          "Mức phạt tiền", "Áp dụng với người lái ô tô vượt đèn đỏ"]
    assert ix._loc_trung(ds) == ["Mức phạt tiền tại khoản 3 Điều 6 Nghị định 168/2024.", "Áp dụng với người lái ô tô vượt đèn đỏ"]
    vs = _versions()
    ids = [u["vid"] for u in ix.don_vi_van_ban(vs, gioi_han=4)]
    assert len(ids) == 4 and ids[0].startswith("ND168_2024.D6.K0") and ids[-1].startswith("ND168_2024.D6.K9")
