"""B2 – Local search theo GraphRAG GỐC của Microsoft (LocalSearchMixedContext, microsoft/graphrag 3.x).

Chỉ mục: scripts/05_ms_graphrag_index.py --ban goc (bảng msg_*). Các bước giống bản gốc:
  1. map_query_to_entities: embedding câu hỏi, lấy top_k_entities × 2 thực thể gần nhất (oversample_scaler = 2).
  2. Ngân sách max_context_tokens = 12.000 chia: báo cáo cộng đồng 15%, text unit 50%, thực thể + quan hệ phần còn lại.
  3. Reports: mọi cộng đồng chứa thực thể đã chọn, xếp theo (số thực thể khớp, rating) giảm dần, thêm full_content
     tới hết ngân sách.
  4. Entities: bảng id|entity|description|number of relationships. Relationships: quan hệ trong nhóm (xếp theo
     combined_degree) + quan hệ ra ngoài (xếp theo số liên kết tới nhóm, rồi combined_degree), tối đa
     top_k_relationships × số thực thể; thêm dần thực thể tới khi vượt ngân sách.
  5. Sources: text unit của từng thực thể theo thứ tự thực thể, trong cùng thực thể ưu tiên text unit chứa nhiều quan hệ
     của thực thể đó; thêm tới hết ngân sách.
  6. LOCAL_SEARCH_SYSTEM_PROMPT nguyên văn (response_type = "multiple paragraphs"); câu hỏi là tin nhắn người dùng.
Không lọc theo ngày áp dụng (bản gốc không có khái niệm hiệu lực). Trích dẫn [Data: Sources (…)] được đổi về mã điều
khoản để chấm cùng bộ độ đo với hai hệ thống còn lại.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from collections.abc import Iterator
from datetime import date

from graphrag.llm import LLM
from graphrag.ms_graphrag import prompts_goc as PG
from graphrag.ms_graphrag.indexing_goc import so_token
from graphrag.pipeline import chi_tiet as CT
from graphrag.pipeline import graph_rag, prompts
from graphrag.pipeline import intent as intent_mod
from graphrag.storage import msg_store

STEPS = {
    "intent": graph_rag.STEPS["intent"],
    "rewrite": graph_rag.STEPS["rewrite"],
    "entities": "Tìm thực thể liên quan (map_query_to_entities)",
    "expand": "Quan hệ của thực thể (trong nhóm và ra ngoài)",
    "community": "Báo cáo cộng đồng chứa các thực thể",
    "units": "Text unit gắn với thực thể (không lọc theo ngày)",
    "context": "Ghép ngữ cảnh theo ngân sách token (Reports, Entities, Relationships, Sources)",
    "generate": "Sinh câu trả lời (prompt local search gốc)",
}

CHUA_CO_CHI_MUC = ("Chưa có chỉ mục GraphRAG gốc. Chạy `python scripts/05_ms_graphrag_index.py --ban goc` trên máy có "
                   "Docker để dựng chỉ mục rồi thử lại.")

_SOURCES = re.compile(r"Sources\s*\(([^)]*)\)", re.IGNORECASE)


# ---------------------------------------------------------------- các hàm thuần (kiểm thử không cần cơ sở dữ liệu)

def bang(ten: str, cot: list[str], dong: list[list]) -> str:
    return f"-----{ten}-----\n" + "\n".join("|".join(str(x) for x in r) for r in [cot] + dong) + "\n"


def chon_quan_he(chon: list[str], rels: list[dict], top_k: int) -> list[dict]:
    """_filter_relationships của bản gốc (relationship_ranking_attribute = rank = combined_degree)."""
    s = set(chon)
    trong = sorted([r for r in rels if r["nguon"] in s and r["dich"] in s], key=lambda r: -(r["bac_ket_hop"] or 0))
    ngoai = [r for r in rels if (r["nguon"] in s) != (r["dich"] in s)]
    if len(ngoai) <= 1:
        return trong + ngoai
    lien_ket: dict[str, set] = defaultdict(set)      # thực thể ngoài nhóm → các thực thể trong nhóm nối tới nó
    for r in ngoai:
        ngoai_tt, trong_tt = (r["dich"], r["nguon"]) if r["dich"] not in s else (r["nguon"], r["dich"])
        lien_ket[ngoai_tt].add(trong_tt)
    for r in ngoai:
        ngoai_tt = r["nguon"] if r["nguon"] not in s else r["dich"]
        r["links"] = len(lien_ket[ngoai_tt])
    ngoai.sort(key=lambda r: (r["links"], r["bac_ket_hop"] or 0), reverse=True)
    return trong + ngoai[: top_k * len(chon)]


def xep_text_unit(chon: list[str], links: list[dict], rels: list[dict]) -> list[dict]:
    """_build_text_unit_context: [(text unit, thứ tự thực thể, số quan hệ của thực thể có trong text unit)] đã sắp."""
    theo_tt: dict[str, list[dict]] = defaultdict(list)
    for lk in links:
        theo_tt[lk["thuc_the_id"]].append(lk)
    da, out = set(), []
    for i, e in enumerate(chon):
        qh_e = [r for r in rels if e in (r["nguon"], r["dich"])]
        for lk in sorted(theo_tt.get(e, []), key=lambda x: x["ma_ngan"]):
            if lk["vid"] in da:
                continue
            da.add(lk["vid"])
            n = sum(1 for r in qh_e if lk["vid"] in (r.get("vids") or []))
            out.append({**lk, "thu_tu_tt": i, "so_qh": n, "thuc_the": e})
    out.sort(key=lambda x: (x["thu_tu_tt"], -x["so_qh"]))
    return out


def them_toi_han(tieu_de: str, cot: list[str], dong: list[list], toi_da: int) -> tuple[str, int]:
    """Thêm từng dòng tới khi vượt ngân sách token (build_*_context của bản gốc). Trả về (bảng, số dòng đã thêm)."""
    n, text = 0, ""
    for k in range(1, len(dong) + 1):
        t = bang(tieu_de, cot, dong[:k])
        if so_token(t) > toi_da:
            break
        n, text = k, t
    return text, n


def tach_trich_dan(answer: str, ma_ngan_sang_id: dict[int, str]) -> tuple[list[str], list[str]]:
    """[Data: Sources (12, 7, +more)] → mã điều khoản. Số không có trong ngữ cảnh là mã lạ."""
    hop_le, la = [], []
    for m in _SOURCES.finditer(answer or ""):
        for x in re.findall(r"\d+", m.group(1)):
            uid = ma_ngan_sang_id.get(int(x))
            if uid and uid not in hop_le:
                hop_le.append(uid)
            elif not uid and f"Sources {x}" not in la:
                la.append(f"Sources {x}")
    return hop_le, la


# ---------------------------------------------------------------- pipeline

def _chi_muc_san_sang(conn) -> bool:
    try:
        return msg_store.dem(conn).get("msg_thuc_the", 0) > 0
    except Exception:  # noqa: BLE001
        conn.rollback()
        return False


def run(res, question: str, ngay: date | None = None, history: list[dict] | None = None, che_do: str = "local",
        stream: bool = False, **_) -> Iterator[dict]:
    cfg = res.cfg
    g = cfg.get("ms_graphrag_goc", {})
    ngay = ngay or date.today()
    t_start = time.perf_counter()
    steps: list[dict] = []

    def step(key: str, t0: float, detail: str, **data) -> dict:
        ev = {"type": "step", "key": key, "label": STEPS.get(key, key), "ms": graph_rag._ms(t0), "detail": detail, **data}
        steps.append({k: v for k, v in ev.items() if k != "type"})
        return ev

    label, q = yield from graph_rag.tien_xu_ly(res, question, history, step)
    if label != intent_mod.LUAT:
        yield from graph_rag.tra_loi_mau(label, question, q, ngay, steps, t_start, stream)
        return

    def done(answer_text: str, **kw) -> dict:
        base = {"type": "done", "intent": intent_mod.LUAT, "che_do": che_do, "question": question,
                "question_rewritten": q if q != question.strip() else None, "date": ngay.isoformat(),
                "answer": answer_text, "citations": [], "unknown_citations": [], "units": [],
                "graph": {"nodes": [], "edges": []}, "notes": [], "retrieved_ids": [], "steps": steps}
        base.update(kw)
        base["latency_s"] = round(time.perf_counter() - t_start, 3)
        return base

    with res.pg_pool.connection() as conn:
        san_sang = _chi_muc_san_sang(conn)
    if not san_sang:
        if stream:
            yield {"type": "token", "text": CHUA_CO_CHI_MUC}
        yield done(CHUA_CO_CHI_MUC)
        return

    qvec = res.embedder.encode_queries([q])[0]
    if che_do == "global":   # global search dùng lại phần map-reduce của B2, đọc bảng msg_*
        from graphrag.pipeline import ms_graphrag

        yield from ms_graphrag._global(res, q, qvec, cfg.get("ms_graphrag", {}), step, stream, done, store=msg_store)
        return
    yield from _local(res, q, qvec, ngay, g, step, stream, done)


def _local(res, q, qvec, ngay, g, step, stream, done):
    top_k = g.get("top_k_entities", 10)
    max_ctx = g.get("max_context_tokens", 12000)
    ngs_cd = int(max_ctx * g.get("community_prop", 0.15))
    ngs_tu = int(max_ctx * g.get("text_unit_prop", 0.5))
    ngs_local = int(max_ctx * (1 - g.get("community_prop", 0.15) - g.get("text_unit_prop", 0.5)))

    # 1. Thực thể
    t0 = time.perf_counter()
    with res.pg_pool.connection() as conn:
        ents = msg_store.tim_thuc_the(conn, qvec, k=top_k * 2)
    chon = [e["id"] for e in ents]
    yield step("entities", t0, f"{len(ents)} thực thể: " + ", ".join(e["ten"] for e in ents[:5])
               + ("…" if len(ents) > 5 else ""), entities=chon, chi_tiet=CT.ct(
        [f"Mã hóa câu hỏi bằng {res.cfg['embedding']['model']}, so cosine với embedding \"tên:mô tả\" của thực thể.",
         f"Như bản gốc: lấy top_k_entities × 2 = {top_k * 2} thực thể (oversample_scaler = 2) và dùng tất cả."],
        [["top_k_entities", top_k]],
        [CT.bang("Thực thể gần câu hỏi nhất", ["#", "Thực thể", "Loại", "Cosine"],
                 [CT.dong([n, e["ten"], e["loai"], CT.so(e.get("diem"), 4)], noi_dung=e.get("mo_ta"))
                  for n, e in enumerate(ents, 1)])]))

    with res.pg_pool.connection() as conn:
        rels = msg_store.quan_he_cua(conn, chon) if chon else []
        comms = msg_store.cong_dong_chua(conn, chon) if chon else []
        links = msg_store.text_unit_cua(conn, chon) if chon else []
        ten = msg_store.ten_thuc_the(conn, list({r["nguon"] for r in rels} | {r["dich"] for r in rels} | set(chon)))
    e_by = {e["id"]: e for e in ents}

    # 2. Báo cáo cộng đồng
    t0 = time.perf_counter()
    comms.sort(key=lambda c: (c["so_khop"], c["muc_do"] or 0), reverse=True)
    txt_cd, n_cd = them_toi_han("Reports", ["id", "title", "content"],
                                [[c["id"], c["tieu_de"], c["bao_cao"] or ""] for c in comms], ngs_cd)
    cd_dung = comms[:n_cd]

    # 3. Thực thể + quan hệ
    t1 = time.perf_counter()
    txt_tt, n_tt = them_toi_han("Entities", ["id", "entity", "description", "number of relationships"],
                                [[e["ma_ngan"], e["ten"], e["mo_ta"] or "", e["bac"]] for e in ents], ngs_local)
    tok_tt = so_token(txt_tt)
    txt_qh, qh_dung = "", []
    for k in range(1, len(chon) + 1):
        ds = chon_quan_he(chon[:k], [dict(r) for r in rels], g.get("top_k_relationships", 10))
        t = bang("Relationships", ["id", "source", "target", "description", "weight"],
                 [[r["ma_ngan"], ten.get(r["nguon"], r["nguon"]), ten.get(r["dich"], r["dich"]), r["mo_ta"] or "",
                   r["trong_so"]] for r in ds])
        if tok_tt + so_token(t) > ngs_local:
            break
        txt_qh, qh_dung = t, ds
    yield step("expand", t1, f"{len(qh_dung)} quan hệ (trong nhóm và ra ngoài)", chi_tiet=CT.ct(
        ["Quan hệ trong nhóm (cả hai đầu là thực thể đã chọn) xếp theo combined_degree; quan hệ ra ngoài xếp theo số "
         "thực thể trong nhóm nối tới đầu kia, rồi combined_degree; giữ tối đa top_k_relationships × số thực thể.",
         f"Thực thể và quan hệ dùng chung {ngs_local} token."],
        [["top_k_relationships", g.get("top_k_relationships", 10)], ["Quan hệ xét", len(rels)], ["Giữ", len(qh_dung)]],
        [CT.bang("Quan hệ đưa vào ngữ cảnh", ["Nguồn", "Đích", "Trọng số"],
                 [CT.dong([ten.get(r["nguon"], r["nguon"]), ten.get(r["dich"], r["dich"]), CT.so(r["trong_so"], 1)],
                          noi_dung=r["mo_ta"]) for r in qh_dung[:60]])]))
    yield step("community", t0, f"{len(cd_dung)}/{len(comms)} báo cáo cộng đồng"
               + (": " + "; ".join(c["tieu_de"] for c in cd_dung) if cd_dung else ""), chi_tiet=CT.ct(
        ["Mọi cộng đồng (mọi cấp) chứa thực thể đã chọn, xếp theo số thực thể khớp rồi rating; thêm full_content của "
         f"báo cáo tới khi hết {ngs_cd} token (community_prop = {g.get('community_prop', 0.15)})."],
        [["Cộng đồng chứa thực thể", len(comms)], ["Đưa vào ngữ cảnh", len(cd_dung)]],
        [CT.bang("Báo cáo cộng đồng", ["Mã", "Cấp", "Tiêu đề", "Rating", "Khớp"],
                 [CT.dong([c["id"], c["cap"], c["tieu_de"], CT.so(c.get("muc_do"), 1), c["so_khop"]],
                          noi_dung=c.get("tom_tat"), kieu="giu" if c in cd_dung else "bo") for c in comms[:30]])]))

    # 4. Text unit (Sources)
    t0 = time.perf_counter()
    xep = xep_text_unit(chon, links, rels)
    with res.pg_pool.connection() as conn:
        pb = msg_store.phien_ban(conn, [x["vid"] for x in xep[:200]]) if xep else {}
    xep = [x for x in xep if x["vid"] in pb]
    txt_src, n_src = them_toi_han("Sources", ["id", "text"],
                                  [[x["ma_ngan"], graph_rag._text(pb[x["vid"]]).replace("\n", " ")] for x in xep], ngs_tu)
    src = xep[:n_src]
    retrieved = list(dict.fromkeys(x["don_vi_id"] for x in src))
    yield step("units", t0, f"{len(xep)} text unit gắn với thực thể → đưa {len(src)} vào ngữ cảnh "
               f"({len(retrieved)} điều khoản, không lọc theo ngày)", seeds=retrieved, chi_tiet=CT.ct(
        ["Lấy text unit của từng thực thể theo thứ tự thực thể; trong cùng thực thể, text unit chứa nhiều quan hệ của "
         "thực thể đó đứng trước.",
         f"Thêm tới khi hết {ngs_tu} token (text_unit_prop = {g.get('text_unit_prop', 0.5)}). Bản gốc không lọc theo "
         "ngày áp dụng nên có thể có cả phiên bản cũ và phiên bản sau sửa đổi của cùng một điều khoản."],
        [["Text unit ứng viên", len(xep)], ["Đưa vào ngữ cảnh", len(src)]],
        [CT.bang("Sources", ["id", "Điều khoản", "Thực thể", "Số quan hệ"],
                 [CT.dong([x["ma_ngan"], CT.nhan(x["don_vi_id"]), e_by.get(x["thuc_the"], {}).get("ten", x["thuc_the"]),
                           x["so_qh"]], x["don_vi_id"], graph_rag._text(pb[x["vid"]]),
                          "giu" if k < n_src else "bo") for k, x in enumerate(xep[:80])])]))

    # 5. Ghép ngữ cảnh
    t0 = time.perf_counter()
    context_data = "\n\n".join(t for t in (txt_cd, txt_tt + ("\n" + txt_qh if txt_qh else ""), txt_src) if t)
    system = PG.LOCAL_SEARCH_SYSTEM_PROMPT.format(context_data=context_data,
                                                  response_type=g.get("response_type", "multiple paragraphs"))
    ma_sang_id = {x["ma_ngan"]: x["don_vi_id"] for x in src}
    units = [{**pb[x["vid"]], "ma_ngan": x["ma_ngan"]} for x in src]
    out_units = [graph_rag._serialize_unit(u, {"origin": "entity", "score": None, "ma_ngan": u["ma_ngan"],
                                               "via": {"type": "THUC_THE", "kind": "THUC_THE", "hops": 0,
                                                       "from": e_by.get(src[k]["thuc_the"], {}).get("ten")},
                                               "sua_doi": [], "cited": False}) for k, u in enumerate(units)]
    graph_ctx = {
        "thuc_the": [{"id": e["id"], "ten": e["ten"], "loai": e["loai"], "mo_ta": e["mo_ta"], "vai_tro": "khop"}
                     for e in ents[:n_tt]],
        "quan_he": [{k: r[k] for k in ("nguon", "dich", "mo_ta", "trong_so")} for r in qh_dung],
        "cong_dong": [{k: c[k] for k in ("id", "cap", "tieu_de", "tom_tat", "muc_do")} for c in cd_dung],
    }
    yield step("context", t0, f"{so_token(context_data):,} token: {n_cd} báo cáo, {n_tt} thực thể, {len(qh_dung)} quan hệ, "
               f"{n_src} text unit".replace(",", "."), chi_tiet=CT.ct(
        [f"max_context_tokens = {max_ctx}: Reports {ngs_cd}, Entities + Relationships {ngs_local}, Sources {ngs_tu} "
         "token. Các bảng ghép theo thứ tự Reports → Entities → Relationships → Sources, cột phân cách bằng \"|\"."],
        [["Báo cáo", n_cd], ["Thực thể", n_tt], ["Quan hệ", len(qh_dung)], ["Text unit", n_src],
         ["Độ dài ngữ cảnh", f"{so_token(context_data)} token"]]))
    yield {"type": "context", "question": q, "date": ngay.isoformat(), "units": out_units,
           "graph": _graph_payload(out_units, graph_ctx), "notes": [], "graph_context": graph_ctx}

    # 6. Sinh câu trả lời
    t0 = time.perf_counter()
    llm = LLM(res.llm.client, res.llm.model, res.llm.temperature, g.get("answer_max_tokens", 2000),
              getattr(res.llm, "reasoning_effort", None))
    if not src and not cd_dung and not n_tt:
        answer_text = "I don't know."
        if stream:
            yield {"type": "token", "text": answer_text}
    elif stream:
        parts = []
        for chunk in llm.generate_stream(system, q):
            parts.append(chunk)
            yield {"type": "token", "text": chunk}
        answer_text = "".join(parts)
    else:
        answer_text = llm.generate(system, q)
    citations, unknown = tach_trich_dan(answer_text, ma_sang_id)
    yield step("generate", t0, f"{len(citations)} điều khoản được trích (Sources)"
               + (f", {len(unknown)} id lạ" if unknown else ""), chi_tiet=CT.ct(
        ["Prompt hệ thống là LOCAL_SEARCH_SYSTEM_PROMPT nguyên văn của Microsoft (chứa ngữ cảnh), tin nhắn người dùng "
         "là câu hỏi. Mô hình trích dẫn dạng [Data: Sources (id); Entities (id); …].",
         "Các id trong Sources (…) được đổi về mã điều khoản để chấm cùng độ đo với hai hệ thống còn lại."],
        [["Mô hình", res.llm.model], ["Tối đa token trả lời", g.get("answer_max_tokens", 2000)],
         ["response_type", g.get("response_type", "multiple paragraphs")]],
        [CT.bang("Trích dẫn Sources", ["Mã", "Điều khoản", "Kết quả"],
                 [CT.dong([CT.nhan(i), prompts.ten_dieu_khoan(i), "Hợp lệ"], i, kieu="giu") for i in citations]
                 + [CT.dong([i, "", "Không có trong ngữ cảnh"], kieu="bo") for i in unknown])]))
    for u in out_units:
        u["cited"] = u["id"] in citations
    yield done(answer_text, citations=citations, unknown_citations=unknown, units=out_units,
               graph=_graph_payload(out_units, graph_ctx), retrieved_ids=retrieved, graph_context=graph_ctx)


def _graph_payload(units: list[dict], gctx: dict) -> dict:
    have = {e["id"] for e in gctx["thuc_the"]}
    nodes = [{"id": "E:" + e["id"], "label": e["ten"][:40], "cap": "ThucThe", "van_ban_id": None, "role": "entity",
              "cited": False, "loai": e["loai"]} for e in gctx["thuc_the"]]
    seen = set()
    for u in units:
        if u["id"] in seen:
            continue
        seen.add(u["id"])
        nodes.append({"id": u["id"], "label": prompts.nhan_ngan(u["id"]), "cap": u.get("cap"),
                      "van_ban_id": u.get("van_ban_id"), "role": "seed", "cited": u.get("cited", False)})
    edges = [{"source": "E:" + r["nguon"], "target": "E:" + r["dich"], "type": "LIEN_QUAN"}
             for r in gctx["quan_he"] if r["nguon"] in have and r["dich"] in have]
    return {"nodes": nodes, "edges": edges}
