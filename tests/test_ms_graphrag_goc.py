"""Kiểm thử B2 theo GraphRAG gốc (không cần DB/mạng): bộ đọc định dạng gốc, gleaning, dựng chỉ mục, local search."""
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from graphrag.common.config import load_config
from graphrag.ms_graphrag import indexing as ix
from graphrag.ms_graphrag import indexing_goc as ig
from graphrag.ms_graphrag import prompts_goc as PG
from graphrag.pipeline import he_thong, ms_graphrag_goc as G

D = date.fromisoformat

RAW = ('("entity"<|>XE Ô TÔ<|>EVENT<|>Phương tiện bị xử phạt)\n##\n'
       '("entity"<|>CẢNH SÁT GIAO THÔNG<|>ORGANIZATION<|>Lực lượng xử phạt)\n##\n'
       '("relationship"<|>CẢNH SÁT GIAO THÔNG<|>XE Ô TÔ<|>Xử phạt người lái xe ô tô<|>8)\n<|COMPLETE|>')


def test_prompt_goc_nguyen_van():
    assert "Return output in English" in PG.GRAPH_EXTRACTION_PROMPT
    assert PG.GRAPH_EXTRACTION_PROMPT.format(entity_types="organization", input_text="x").count("Entity_types") == 4
    assert "{max_report_length}" in PG.COMMUNITY_REPORT_PROMPT and "{context_data}" in PG.LOCAL_SEARCH_SYSTEM_PROMPT


def test_doc_ket_qua_dinh_dang_goc():
    kq = ig.doc_ket_qua(RAW)
    assert [e["ten"] for e in kq["thuc_the"]] == ["XE Ô TÔ", "CẢNH SÁT GIAO THÔNG"]
    assert kq["quan_he"] == [{"nguon": "CẢNH SÁT GIAO THÔNG", "dich": "XE Ô TÔ", "mo_ta": "Xử phạt người lái xe ô tô",
                              "do_manh": 8.0}]       # quan hệ cuối trước <|COMPLETE|> vẫn đọc được độ mạnh


class FakeChat:
    """Ghi lại các tin nhắn: lượt 1 trả RAW, lượt gleaning trả thêm một thực thể."""

    def __init__(self):
        self.calls = []

    def generate_messages(self, msgs):
        self.calls.append([m["role"] for m in msgs])
        last = msgs[-1]["content"]
        if last == PG.CONTINUE_PROMPT:
            return '("entity"<|>BỘ CÔNG AN<|>ORGANIZATION<|>Cơ quan quản lý)<|COMPLETE|>'
        if "-Real Data-" in last:
            return RAW
        if "Description List" in last:
            return "Mô tả tổng hợp."
        if "community" in last.lower():
            return ('{"title": "Xử phạt ô tô", "summary": "Tóm tắt", "rating": 6.5, "rating_explanation": "x", '
                    '"findings": [{"summary": "Ý 1", "explanation": "Giải thích [Data: Entities (1)]"}]}')
        return ""


def test_gleaning_hoi_thoai_nhieu_luot():
    llm = FakeChat()
    out = ig.goi_trich_xuat(llm, "Điều 6 …", ["organization", "person", "geo", "event"], max_gleanings=1)
    assert llm.calls == [["user"], ["user", "assistant", "user"]]     # 1 lượt chính + 1 lượt CONTINUE, không hỏi Y/N
    assert "BỘ CÔNG AN" in out


def test_dung_chi_muc_goc(tmp_path):
    versions = [{"vid": f"ND168_2024.D6.K{i}@2025-01-01", "id": f"ND168_2024.D6.K{i}", "van_ban_id": "ND168_2024",
                 "cap": "Khoan", "noi_dung": f"Phạt tiền người điều khiển xe ô tô vi phạm số {i} theo quy định.",
                 "ngu_canh": "Nghị định 168/2024, Điều 6"} for i in range(1, 4)]
    units = ig.text_units(versions)
    assert [u["ma_ngan"] for u in units] == [1, 2, 3]
    llm = FakeChat()
    kq, loi = ig.trich_xuat(llm, units, ix.Cache(tmp_path / "c.jsonl"), ["organization"], 1, workers=2)
    assert not loi and len(kq) == 3
    tt, qh = ig.gop(kq, {u["vid"]: u["id"] for u in units})
    assert set(tt) == {"xe ô tô", "cảnh sát giao thông", "bộ công an"} and len(qh) == 1
    ig.tom_tat(llm, tt, qh, ix.Cache(tmp_path / "t.jsonl"))
    assert tt["xe ô tô"]["mo_ta_tong"] == "Phương tiện bị xử phạt"     # một mô tả (trùng) → không gọi LLM
    ig.gan_bac(tt, qh)
    comms, _ = ig.cong_dong(tt, qh, 10, 10)
    assert comms and all("bộ công an" not in c["thanh_vien"] for c in comms)   # chỉ thành phần liên thông lớn nhất
    loi = ig.bao_cao_cong_dong(llm, comms, tt, qh, ix.Cache(tmp_path / "b.jsonl"), workers=1)
    assert not loi and comms[0]["bao_cao"]["tieu_de"] == "Xử phạt ô tô" and comms[0]["bao_cao"]["muc_do"] == 6.5
    ig.luu_ket_qua(tmp_path, units, tt, qh, comms, "leiden")
    assert len(ix.doc_jsonl(tmp_path / "text_units.jsonl")) == 3


def test_chon_quan_he_trong_nhom_truoc():
    rels = [{"nguon": "a", "dich": "b", "bac_ket_hop": 2}, {"nguon": "a", "dich": "x", "bac_ket_hop": 9},
            {"nguon": "b", "dich": "x", "bac_ket_hop": 3}, {"nguon": "b", "dich": "y", "bac_ket_hop": 50}]
    out = G.chon_quan_he(["a", "b"], rels, top_k=1)
    assert out[0]["dich"] == "b"                          # trong nhóm trước
    assert [r["dich"] for r in out[1:]] == ["x", "x"]     # x nối với 2 thực thể trong nhóm nên đứng trước y; ngân sách 1×2


def test_tach_trich_dan():
    ok, la = G.tach_trich_dan("Phạt 18 triệu [Data: Sources (2, 7, +more); Entities (5)].", {2: "ND.A", 3: "ND.B"})
    assert ok == ["ND.A"] and la == ["Sources 7"]


class FakePool:
    def connection(self):
        class C:
            def __enter__(s):
                return SimpleNamespace(rollback=lambda: None)

            def __exit__(s, *a):
                return False
        return C()


class FakeLLM:
    def __init__(self):
        self.client, self.model, self.temperature = self, "openai/gpt-6-luna", 0.0
        self.system = None

    def chat(self, model, system, user, temperature, max_tokens, **kw):
        self.system = system
        return "Người lái ô tô bị phạt 18.000.000 – 20.000.000 đồng [Data: Sources (1); Entities (10)]."

    def generate(self, system, user):
        return "PHAP_LUAT" if "phân loại" in system.lower() else user


@pytest.fixture
def res(monkeypatch):
    s = G.msg_store
    monkeypatch.setattr(s, "dem", lambda conn, ten_cu=False: {"msg_thuc_the": 2})
    monkeypatch.setattr(s, "tim_thuc_the", lambda conn, q, k=20: [
        {"id": "đèn đỏ", "ten": "ĐÈN ĐỎ", "loai": "EVENT", "mo_ta": "Vượt đèn đỏ", "bac": 1, "ma_ngan": 10, "diem": .9},
        {"id": "xe ô tô", "ten": "XE Ô TÔ", "loai": "EVENT", "mo_ta": "Ô tô", "bac": 1, "ma_ngan": 11, "diem": .8}])
    monkeypatch.setattr(s, "quan_he_cua", lambda conn, ids: [
        {"nguon": "đèn đỏ", "dich": "xe ô tô", "mo_ta": "ô tô vượt đèn", "trong_so": 7, "tan_suat": 1, "bac_ket_hop": 2,
         "ma_ngan": 5, "vids": ["ND168_2024.D6.K9.b@2025-01-01"]}])
    monkeypatch.setattr(s, "ten_thuc_the", lambda conn, ids: {"đèn đỏ": "ĐÈN ĐỎ", "xe ô tô": "XE Ô TÔ"})
    monkeypatch.setattr(s, "cong_dong_chua", lambda conn, ids: [
        {"id": "0-1", "cap": 0, "tieu_de": "Đèn tín hiệu", "tom_tat": "…", "bao_cao": "# Đèn tín hiệu", "muc_do": 7,
         "so_thanh_vien": 2, "so_khop": 2}])
    monkeypatch.setattr(s, "text_unit_cua", lambda conn, ids: [
        {"thuc_the_id": "đèn đỏ", "vid": "ND168_2024.D6.K9.b@2025-01-01", "don_vi_id": "ND168_2024.D6.K9.b", "ma_ngan": 1},
        {"thuc_the_id": "xe ô tô", "vid": "ND168_2024.D6.K9.b@2026-08-15", "don_vi_id": "ND168_2024.D6.K9.b", "ma_ngan": 2}])

    def pb(conn, vids):
        return {v: {"vid": v, "id": v.split("@")[0], "van_ban_id": "ND168_2024", "cap": "Diem", "tieu_de": None,
                    "noi_dung": "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;", "ngu_canh": "Điều 6 – khoản 9",
                    "hieu_luc_tu": D(v.split("@")[1]), "hieu_luc_den": None, "nguon_sua_doi": None,
                    "loai_phien_ban": "goc"} for v in vids}
    monkeypatch.setattr(s, "phien_ban", pb)
    cfg = load_config("local")
    cfg["ms_graphrag"]["ban"] = "goc"
    llm = FakeLLM()
    return SimpleNamespace(cfg=cfg, embedder=SimpleNamespace(encode_queries=lambda t: np.zeros((1, 4))), llm=llm,
                           pg_pool=FakePool(), bm25=None)


def test_local_search_goc(res):
    out = he_thong.answer(res, "Lái ô tô vượt đèn đỏ bị phạt bao nhiêu?", he_thong="ms_graphrag", ngay=D("2025-06-01"))
    assert out["he_thong"] == "ms_graphrag"
    assert out["retrieved_ids"] == ["ND168_2024.D6.K9.b"]            # hai phiên bản cùng mã → một mã
    assert len(out["units"]) == 2                                      # không lọc theo ngày: giữ cả phiên bản 2026
    assert out["citations"] == ["ND168_2024.D6.K9.b"] and out["unknown_citations"] == []
    sys_prompt = res.llm.system
    assert "---Data tables---" in sys_prompt and "-----Sources-----\nid|text\n1|" in sys_prompt
    assert "-----Reports-----" in sys_prompt and "-----Relationships-----" in sys_prompt
    assert [s["key"] for s in out["steps"]][-6:] == ["entities", "expand", "community", "units", "context", "generate"]
