"""Kiểm thử pipeline GraphRAG không cần DB/mạng: thay PostgreSQL, Neo4j, mô hình bằng bản giả."""
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from graphrag.common.config import load_config
from graphrag.pipeline import conversation, graph_rag
from graphrag.retrieval.query_expansion import expand

D = date.fromisoformat


def unit(uid, noi_dung, tu="2025-01-01", den=None, nguon=None, cap="Diem"):
    return {"vid": f"{uid}@{tu}", "id": uid, "van_ban_id": uid.split(".")[0], "cap": cap, "tieu_de": None,
            "noi_dung": noi_dung, "ngu_canh": "Nghị định 168/2024/NĐ-CP, Điều 6. Xử phạt … – khoản 9: Phạt tiền "
            "từ 18.000.000 đồng đến 20.000.000 đồng", "hieu_luc_tu": D(tu), "hieu_luc_den": D(den) if den else None,
            "nguon_sua_doi": nguon, "loai_phien_ban": "goc"}


VERSIONS = [
    unit("ND168_2024.D6.K9.b", "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;"),
    unit("ND168_2024.D6.K16.b", "Thực hiện hành vi quy định tại … điểm b khoản 9 Điều này bị trừ 04 điểm;"),
    unit("ND168_2024.D6.K3.m", "Chở trẻ em dưới 10 tuổi …", tu="2026-01-01", den="2026-08-15"),
    unit("ND168_2024.D6.K3.m", "Chở trẻ em dưới 10 tuổi … (trừ xe ô tô chỉ có một hàng ghế);", tu="2026-08-15",
         nguon="ND238_2026.D2.K2"),
    unit("ND168_2024.D6.K9", "Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng đối với …", cap="Khoan"),
]


def _valid(ids, ngay):
    return [v for v in VERSIONS if v["id"] in ids and v["hieu_luc_tu"] <= ngay
            and (v["hieu_luc_den"] is None or ngay < v["hieu_luc_den"])]


class FakeLLM:
    def __init__(self):
        self.calls = []

    def generate(self, system, user):
        self.calls.append(user)
        if "CÂU HỎI ĐẦY ĐỦ" in user:
            return "Xe máy vượt đèn đỏ bị phạt bao nhiêu?"
        return "Phạt 18.000.000 – 20.000.000 đồng [ND168_2024.D6.K9.b], trừ 04 điểm [ND168_2024.D6.K16.b] [XX1_2024.D1]."

    def generate_stream(self, system, user):
        for w in self.generate(system, user).split(" "):
            yield w + " "


class FakePool:
    def connection(self):
        class C:
            def __enter__(s):
                return object()

            def __exit__(s, *a):
                return False
        return C()


@pytest.fixture
def res(monkeypatch):
    pg = graph_rag.postgres
    monkeypatch.setattr(pg, "vector_search", lambda conn, q, k=50: [("ND168_2024.D6.K3.m@2026-08-15", 0.9),
                                                                     ("ND168_2024.D6.K9.b@2025-01-01", 0.8)])
    monkeypatch.setattr(pg, "fetch_valid", lambda conn, ids, ngay: _valid(ids, ngay))
    monkeypatch.setattr(pg, "get_units", lambda conn, ids: [v for v in VERSIONS if v["id"] in ids])
    monkeypatch.setattr(pg, "latest_versions", lambda conn, ids: {v["id"]: v for v in VERSIONS if v["id"] in ids})
    paths = [{"seed": "ND168_2024.D6.K9.b", "id": "ND168_2024.D6.K16.b", "cap": "Diem", "hops": 1,
              "rels": [{"src": "ND168_2024.D6.K16.b", "type": "THAM_CHIEU", "dst": "ND168_2024.D6.K9.b"}]},
             {"seed": "ND168_2024.D6.K9.b", "id": "ND168_2024.D6.K9", "cap": "Khoan", "hops": 1,
              "rels": [{"src": "ND168_2024.D6.K9.b", "type": "THUOC", "dst": "ND168_2024.D6.K9"}]}]
    monkeypatch.setattr(graph_rag.neo4j_store, "expand_paths", lambda d, seeds, hops, et: paths)
    monkeypatch.setattr(graph_rag.neo4j_store, "amended_by", lambda d, ids: [
        {"id": "ND168_2024.D6.K3.m", "loai": "SUA_DOI", "nguon": "ND238_2026.D2.K2", "ngay_hieu_luc": "2026-08-15"}])
    monkeypatch.setattr(graph_rag, "rerank", lambda cfg, q, pool, top_n=10: [(i, 0.9) for i, _ in pool[:top_n]])
    bm25 = SimpleNamespace(search=lambda q, k=50: [("ND168_2024.D6.K9.b@2025-01-01", 5.0)])
    emb = SimpleNamespace(encode_queries=lambda t: np.zeros((1, 4)))
    return SimpleNamespace(cfg=load_config("local"), bm25=bm25, embedder=emb, llm=FakeLLM(), pg_pool=FakePool(),
                           neo4j=object())


def test_answer_seed_graph_and_citations(res):
    out = graph_rag.answer(res, "Ô tô vượt đèn đỏ bị phạt bao nhiêu?", ngay=D("2026-09-01"))
    ids = [u["id"] for u in out["units"]]
    assert ids[:2] == ["ND168_2024.D6.K9.b", "ND168_2024.D6.K3.m"]          # seed theo thứ tự rerank
    assert "ND168_2024.D6.K16.b" in ids                                     # thêm nhờ cạnh THAM_CHIEU
    k16 = next(u for u in out["units"] if u["id"] == "ND168_2024.D6.K16.b")
    assert k16["origin"] == "graph" and k16["via"]["type"] == "THAM_CHIEU"
    m = next(u for u in out["units"] if u["id"] == "ND168_2024.D6.K3.m")
    assert m["vid"].endswith("@2026-08-15") and m["nguon_ten"].startswith("khoản 2 Điều 2")   # phiên bản sau sửa đổi
    assert out["citations"] == ["ND168_2024.D6.K9.b", "ND168_2024.D6.K16.b"]
    assert out["unknown_citations"] == ["XX1_2024.D1"]
    assert {e["type"] for e in out["graph"]["edges"]} == {"THAM_CHIEU", "THUOC"}
    assert [s["key"] for s in out["steps"]] == ["intent", "search", "rerank", "graph", "context", "generate"]


def test_not_yet_valid_note(res):
    out = graph_rag.answer(res, "Chở trẻ em ngồi ghế trước bị phạt không?", ngay=D("2025-10-01"))
    assert all(u["id"] != "ND168_2024.D6.K3.m" for u in out["units"])     # chưa có hiệu lực → không vào ngữ cảnh
    assert out["notes"][0]["id"] == "ND168_2024.D6.K3.m" and out["notes"][0]["ngay"] == "2026-01-01"
    assert "chưa có hiệu lực, có hiệu lực từ ngày 01/01/2026" in res.llm.calls[-1]


def test_stream_events_and_conversation(res):
    hist = [{"role": "user", "content": "Ô tô vượt đèn đỏ bị phạt bao nhiêu?"},
            {"role": "assistant", "content": "Phạt 18–20 triệu [ND168_2024.D6.K9.b]"}]
    evs = list(graph_rag.run(res, "Còn xe máy thì sao?", ngay=D("2026-09-01"), history=hist, stream=True))
    types = [e["type"] for e in evs]
    assert types[0] == "step" and evs[0]["key"] == "rewrite" and "Xe máy vượt đèn đỏ" in evs[0]["detail"]
    assert "context" in types and types.count("token") > 3 and types[-1] == "done"
    assert evs[-1]["question_rewritten"] == "Xe máy vượt đèn đỏ bị phạt bao nhiêu?"


def test_graph_failure_still_answers(res, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("neo4j down")
    monkeypatch.setattr(graph_rag.neo4j_store, "expand_paths", boom)
    out = graph_rag.answer(res, "Ô tô vượt đèn đỏ bị phạt bao nhiêu?", ngay=D("2026-09-01"))
    assert out["answer"] and all(u["origin"] == "seed" for u in out["units"])
    assert "Neo4j lỗi" in next(s for s in out["steps"] if s["key"] == "graph")["detail"]


def test_amend_instructions_excluded():
    assert graph_rag._is_amend_instruction({"noi_dung": "Sửa đổi, bổ sung điểm m khoản 3 như sau: …"})
    assert graph_rag._is_amend_instruction({"noi_dung": "Bãi bỏ điểm d, điểm đ khoản 17 Điều 32."})
    assert not graph_rag._is_amend_instruction({"noi_dung": "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;"})


def test_rewrite_skipped_without_history():
    llm = FakeLLM()
    assert conversation.rewrite_question(llm, [], "Ô tô vượt đèn đỏ?") == "Ô tô vượt đèn đỏ?" and not llm.calls


def test_query_expansion():
    q = expand("Xe máy vượt đèn đỏ bị phạt bao nhiêu?")
    assert "không chấp hành hiệu lệnh của đèn tín hiệu giao thông" in q and "xe mô tô xe gắn máy" in q
    assert expand("Thủ tục đăng ký kết hôn") == "Thủ tục đăng ký kết hôn"


# ---------------- Phân loại câu hỏi ----------------
from graphrag.pipeline import intent as intent_mod  # noqa: E402


class LabelLLM:
    def __init__(self, label):
        self.label, self.calls = label, 0

    def generate(self, system, user):
        self.calls += 1
        return self.label


@pytest.mark.parametrize("q,label", [
    ("Xin chào", "chao"), ("chào bạn nhé", "chao"), ("hello", "chao"), ("Cảm ơn bạn nhiều!", "cam_on"),
    ("tạm biệt", "tam_biet"), ("Bạn là ai?", "gioi_thieu"), ("ban lam duoc gi", "gioi_thieu"),
])
def test_social_by_rules(q, label):
    llm = LabelLLM("NGOAI")
    assert intent_mod.classify(q, llm) == (label, "luật") and llm.calls == 0


@pytest.mark.parametrize("q", ["Ô tô vượt đèn đỏ bị phạt bao nhiêu?", "Còn xe máy thì sao?", "bằng lái bị trừ hết điểm",
                               "Xin chào, chạy quá tốc độ 20 km/h phạt bao nhiêu?", "uong ruou lai xe phat bao nhieu"])
def test_traffic_by_keywords(q):
    llm = LabelLLM("NGOAI")
    assert intent_mod.classify(q, llm) == ("luat", "luật") and llm.calls == 0


def test_off_topic_uses_llm():
    assert intent_mod.classify("Giá vàng hôm nay bao nhiêu?", LabelLLM("NGOAI")) == ("ngoai_pham_vi", "LLM")
    assert intent_mod.classify("Có nên mua cổ phiếu VNM không?", LabelLLM("NGOAI")) == ("ngoai_pham_vi", "LLM")
    assert intent_mod.classify("Quy định này áp dụng từ khi nào?", LabelLLM("LUAT")) == ("luat", "LLM")


def test_llm_error_does_not_block():
    class Broken:
        def generate(self, s, u):
            raise RuntimeError("down")
    assert intent_mod.classify("Thủ tục công chứng?", Broken()) == ("luat", "mặc định")


def test_pipeline_greeting_and_off_topic_skip_retrieval(res):
    res.bm25 = SimpleNamespace(search=lambda q, k=50: pytest.fail("không được tra cứu"))
    out = graph_rag.answer(res, "Xin chào")
    assert out["intent"] == "chao" and out["units"] == [] and "Xin chào" in out["answer"]
    evs = list(graph_rag.run(res, "Cảm ơn nhé", stream=True))
    assert [e["type"] for e in evs][0] == "step" and evs[-1]["intent"] == "cam_on"
    assert "".join(e["text"] for e in evs if e["type"] == "token") == evs[-1]["answer"]
    res.llm = LabelLLM("NGOAI")
    out = graph_rag.answer(res, "Giá vàng hôm nay thế nào?")
    assert out["intent"] == "ngoai_pham_vi" and "không thuộc phạm vi" in out["answer"]
