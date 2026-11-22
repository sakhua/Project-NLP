"""B2 – GraphRAG kiểu Microsoft (Edge và cộng sự, 2024), cài đặt lại. Chỉ mục: scripts/05_ms_graphrag_index.py.

Local search (mặc định, dùng để đánh giá):
  1. Embedding câu hỏi → các thực thể có mô tả gần nhất (vector trên ms_thuc_the).
  2. Mở rộng đồ thị thực thể: thêm thực thể lân cận theo quan hệ có trọng số lớn (hops = 1).
  3. Ngữ cảnh gồm: thực thể, quan hệ (trong nhóm trước, ra ngoài sau), báo cáo cộng đồng chứa các thực thể đó,
     và các đơn vị văn bản (khoản/điểm) gắn với thực thể, xếp theo thứ hạng thực thể.
  4. Đơn vị văn bản lọc theo ngày áp dụng như hai hệ thống còn lại (tắt bằng use_temporal_filter=False để chạy
     "GraphRAG nguyên bản"), rồi sinh câu trả lời bằng cùng prompt, cùng cách trích dẫn mã điều khoản.
  KHÔNG dùng BM25, không dùng vector trên điều khoản, không rerank, không dùng đồ thị văn bản (THAM_CHIEU…).

Global search (map-reduce trên báo cáo cộng đồng, cho câu hỏi tổng quan; không lọc theo ngày, không trích mã điều khoản):
  chọn cộng đồng ở một cấp → map: mỗi nhóm báo cáo cho ra các ý có điểm → reduce: tổng hợp câu trả lời.
"""
from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from graphrag.ms_graphrag import prompts as MP
from graphrag.ms_graphrag.indexing import doc_json
from graphrag.pipeline import chi_tiet as CT
from graphrag.pipeline import graph_rag, prompts
from graphrag.pipeline import intent as intent_mod
from graphrag.storage import ms_store, postgres

STEPS = {
    "intent": graph_rag.STEPS["intent"],
    "rewrite": graph_rag.STEPS["rewrite"],
    "entities": "Tìm thực thể liên quan (vector trên mô tả thực thể)",
    "expand": "Mở rộng sang thực thể lân cận trên đồ thị thực thể",
    "community": "Lấy báo cáo cộng đồng chứa các thực thể",
    "units": "Lấy điều khoản gắn với thực thể, lọc theo ngày áp dụng",
    "context": "Ghép ngữ cảnh: điều khoản + thực thể, quan hệ, cộng đồng",
    "generate": "Sinh câu trả lời có trích dẫn",
    "communities": "Chọn báo cáo cộng đồng (global search)",
    "map": "Map: rút ý từ từng nhóm báo cáo",
    "reduce": "Reduce: tổng hợp câu trả lời",
}

CHUA_CO_CHI_MUC = ("Chưa có chỉ mục GraphRAG (baseline kiểu Microsoft). Chạy `python scripts/05_ms_graphrag_index.py` "
                   "trên máy có Docker để dựng chỉ mục rồi thử lại.")


def _cat(rows: list[str], toi_da: int) -> list[str]:
    out, n = [], 0
    for r in rows:
        if n + len(r) > toi_da:
            break
        out.append(r)
        n += len(r) + 1
    return out


def _chi_muc_san_sang(conn) -> bool:
    try:
        return ms_store.dem(conn).get("ms_thuc_the", 0) > 0
    except Exception:  # noqa: BLE001
        conn.rollback()
        return False


def run(res, question: str, ngay: date | None = None, history: list[dict] | None = None,
        che_do: str = "local", hops: int | None = None, use_temporal_filter: bool = True,
        stream: bool = False, **_) -> Iterator[dict]:
    """Phát sự kiện cùng dạng graph_rag.run (step / context / token / done).
    ms_graphrag.ban = "goc" (mặc định): chạy bản GraphRAG gốc (pipeline/ms_graphrag_goc.py, bảng msg_*);
    "luat": bản đã chỉnh cho luật giao thông dưới đây (bảng ms_*)."""
    cfg = res.cfg
    mc = cfg.get("ms_graphrag", {})
    if mc.get("ban", "goc") == "goc":
        from graphrag.pipeline import ms_graphrag_goc

        yield from ms_graphrag_goc.run(res, question, ngay=ngay, history=history, che_do=che_do, stream=stream)
        return
    ngay = ngay or date.today()
    hops = mc.get("hops", 1) if hops is None else hops
    t_start = time.perf_counter()
    steps: list[dict] = []

    def step(key: str, t0: float, detail: str, **data) -> dict:
        ev = {"type": "step", "key": key, "label": STEPS[key], "ms": graph_rag._ms(t0), "detail": detail, **data}
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
    if che_do == "global":
        yield from _global(res, q, qvec, mc, step, stream, done)
    else:
        yield from _local(res, q, qvec, ngay, mc, hops, use_temporal_filter, step, stream, done)


# ---------------------------------------------------------------- local search

def _local(res, q, qvec, ngay, mc, hops, use_temporal_filter, step, stream, done):
    t0 = time.perf_counter()
    with res.pg_pool.connection() as conn:
        seeds = ms_store.tim_thuc_the(conn, qvec, k=mc.get("top_k_entities", 10))
    seed_ids = [e["id"] for e in seeds]
    yield step("entities", t0, f"{len(seeds)} thực thể: " + ", ".join(e["ten"] for e in seeds[:5])
               + ("…" if len(seeds) > 5 else ""), entities=seed_ids, chi_tiet=CT.ct(
        [f"Mô hình {res.cfg['embedding']['model']} mã hóa câu hỏi; so cosine với embedding mô tả của mọi thực thể "
         "mà LLM đã trích khi dựng chỉ mục (bảng ms_thuc_the).",
         "Không tìm trực tiếp trên điều khoản như hai hệ thống còn lại: mọi điều khoản đều phải đi qua thực thể."],
        [["Số thực thể lấy", mc.get("top_k_entities", 10)]],
        [CT.bang("Thực thể gần câu hỏi nhất", ["#", "Thực thể", "Loại", "Cosine"],
                 [CT.dong([n, e["ten"], e["loai"], CT.so(e.get("diem"), 4)], noi_dung=e.get("mo_ta"))
                  for n, e in enumerate(seeds, 1)], "Bấm một dòng để xem mô tả thực thể.")]))

    # Mở rộng đồ thị thực thể
    t0 = time.perf_counter()
    with res.pg_pool.connection() as conn:
        rels = ms_store.quan_he_cua(conn, seed_ids, limit=300) if seed_ids else []
        nb_w: dict[str, float] = defaultdict(float)
        for r in rels:
            for a, b in ((r["nguon"], r["dich"]), (r["dich"], r["nguon"])):
                if a in seed_ids and b not in seed_ids:
                    nb_w[b] += r["trong_so"] or 0
        nb_ids = [i for i, _ in sorted(nb_w.items(), key=lambda kv: -kv[1])][: mc.get("max_neighbors", 10)] if hops else []
        neighbors = {e["id"]: e for e in ms_store.lay_thuc_the(conn, nb_ids)} if nb_ids else {}
        comms = ms_store.cong_dong_cua(conn, seed_ids, limit=mc.get("top_communities", 3)) if seed_ids else []
        links = ms_store.don_vi_cua(conn, seed_ids + nb_ids) if seed_ids else []
    nb_list = [neighbors[i] for i in nb_ids if i in neighbors]
    if hops:
        yield step("expand", t0, f"+{len(nb_list)} thực thể lân cận"
                   + (": " + ", ".join(e["ten"] for e in nb_list[:4]) + ("…" if len(nb_list) > 4 else "") if nb_list else ""),
                   chi_tiet=CT.ct(
                       ["Lấy các quan hệ của thực thể khớp câu hỏi (tối đa 300). Mỗi thực thể ở đầu kia được cộng trọng "
                        "số của các quan hệ nối với nhóm thực thể khớp.",
                        f"Giữ {mc.get('max_neighbors', 10)} thực thể có tổng trọng số lớn nhất làm thực thể lân cận."],
                       [["Quan hệ xét", len(rels)], ["Ứng viên lân cận", len(nb_w)], ["Giữ", len(nb_list)]],
                       [CT.bang("Thực thể lân cận", ["#", "Thực thể", "Loại", "Tổng trọng số"],
                                [CT.dong([n, e["ten"], e["loai"], CT.so(nb_w.get(e["id"]), 2)], noi_dung=e.get("mo_ta"))
                                 for n, e in enumerate(nb_list, 1)])]))
    yield step("community", t0, f"{len(comms)} báo cáo cộng đồng"
               + (": " + "; ".join(c["tieu_de"] for c in comms) if comms else ""), chi_tiet=CT.ct(
        ["Khi dựng chỉ mục, thuật toán Leiden chia đồ thị thực thể thành cộng đồng (nhóm thực thể liên kết chặt), "
         "nhiều cấp; LLM viết báo cáo tóm tắt cho từng cộng đồng.",
         f"Chọn {mc.get('top_communities', 3)} cộng đồng chứa nhiều thực thể khớp câu hỏi nhất, ưu tiên mức độ quan trọng cao."],
        [["Số cộng đồng lấy", mc.get("top_communities", 3)]],
        [CT.bang("Báo cáo cộng đồng", ["Mã", "Cấp", "Tiêu đề", "Mức độ", "Thành viên"],
                 [CT.dong([c["id"], c["cap"], c["tieu_de"], CT.so(c.get("muc_do"), 1), c.get("so_thanh_vien")],
                          noi_dung=c.get("tom_tat")) for c in comms], "Bấm một dòng để xem tóm tắt.")]))

    # Quan hệ: trong nhóm (cả hai đầu đã chọn) trước, ra ngoài sau; trọng số giảm dần
    chon = set(seed_ids) | set(nb_ids)
    rels_in = [r for r in rels if r["nguon"] in chon and r["dich"] in chon]
    rels_out = [r for r in rels if not (r["nguon"] in chon and r["dich"] in chon)]
    ctx_rels = (rels_in + rels_out)[: mc.get("max_relations", 25)]

    # Đơn vị văn bản: điểm = tổng trọng số của các thực thể nhắc tới (thực thể xếp trên nặng hơn, lân cận nhẹ hơn)
    t0 = time.perf_counter()
    w = {e: 1.0 / (1 + i) for i, e in enumerate(seed_ids)}
    w.update({e: 0.5 / (1 + i) for i, e in enumerate(nb_ids)})
    diem: dict[str, float] = defaultdict(float)
    tu_tt: dict[str, str] = {}
    da = set()
    for lk in links:
        k = (lk["thuc_the_id"], lk["don_vi_id"])
        if k in da:
            continue
        da.add(k)
        diem[lk["don_vi_id"]] += w.get(lk["thuc_the_id"], 0)
        if lk["don_vi_id"] not in tu_tt or w.get(lk["thuc_the_id"], 0) > w.get(tu_tt[lk["don_vi_id"]], 0):
            tu_tt[lk["don_vi_id"]] = lk["thuc_the_id"]
    ranked = [i for i, _ in sorted(diem.items(), key=lambda kv: (-kv[1], kv[0]))][:60]
    with res.pg_pool.connection() as conn:
        if use_temporal_filter:
            valid = {r["id"]: r for r in postgres.fetch_valid(conn, ranked, ngay)} if ranked else {}
            notes = graph_rag._validity_notes(conn, ranked[:10], set(valid), ngay) if ranked else []
        else:
            valid, notes = (postgres.latest_versions(conn, ranked) if ranked else {}), []
    ok = [i for i in ranked if i in valid and valid[i]["cap"] != "Chuong" and not graph_rag._is_amend_instruction(valid[i])]
    unit_ids = ok[: mc.get("top_k_units", 10)]
    ten_tt = {e["id"]: e["ten"] for e in seeds} | {e["id"]: e["ten"] for e in nb_list}
    giu, ok_set, rows = set(unit_ids), set(ok), []
    for n, i in enumerate(ranked[:40], 1):
        kq = ("Giữ" if i in giu else f"Loại: vượt giới hạn {mc.get('top_k_units', 10)}" if i in ok_set
              else "Loại: không có phiên bản hiệu lực" if i not in valid else "Loại: Chương hoặc câu lệnh sửa đổi")
        rows.append(CT.dong([n, CT.nhan(i), ten_tt.get(tu_tt.get(i), tu_tt.get(i)), CT.so(diem[i], 3), kq], i,
                            graph_rag._text(valid[i]) if i in valid else None, "giu" if i in giu else "bo"))
    yield step("units", t0, f"{len(ranked)} điều khoản gắn với thực thể → {len(ok)} còn hiệu lực ngày "
               f"{prompts.ngay_vn(ngay)} → giữ {len(unit_ids)}"
               + (f"; {len(notes)} quy định chưa/hết hiệu lực" if notes else ""), seeds=unit_ids, chi_tiet=CT.ct(
        ["Mỗi thực thể gắn với các điều khoản mà LLM đã trích ra nó (cạnh XUAT_HIEN_TAI).",
         "Điểm của điều khoản = tổng trọng số các thực thể nhắc tới nó: thực thể khớp hạng r có trọng số 1/r, "
         "thực thể lân cận hạng r có trọng số 0,5/r.",
         f"Lọc theo ngày áp dụng {prompts.ngay_vn(ngay)} như hai hệ thống còn lại, bỏ Chương và câu lệnh sửa đổi, "
         f"giữ {mc.get('top_k_units', 10)} điều khoản điểm cao nhất. Không dùng BM25, rerank hay đồ thị văn bản."],
        [["Điều khoản gắn với thực thể", len(ranked)], ["Còn hiệu lực", len(ok)], ["Giữ", len(unit_ids)]],
        [CT.bang("Điều khoản theo điểm thực thể", ["#", "Điều khoản", "Thực thể chính", "Điểm", "Kết quả"], rows,
                 "Bấm một dòng để xem nội dung điều khoản.")]))

    # Ghép ngữ cảnh
    t0 = time.perf_counter()
    ten = {e["id"]: e["ten"] for e in seeds} | {e["id"]: e["ten"] for e in nb_list}
    units = [{**valid[i], "origin": "entity", "score": round(diem[i], 4),
              "via": {"type": "THUC_THE", "kind": "THUC_THE", "from": ten.get(tu_tt.get(i), tu_tt.get(i)), "hops": 0}}
             for i in unit_ids]
    toi_da = mc.get("max_graph_chars", 4000)
    dong_tt = [f"- {e['ten']} ({e['loai']}): {(e['mo_ta'] or '')[:220]}" for e in seeds + nb_list]
    dong_qh = [f"- {ten.get(r['nguon'], r['nguon'])} — {ten.get(r['dich'], r['dich'])}: {(r['mo_ta'] or '')[:200]}"
               for r in ctx_rels]
    dong_cd = [f"- {c['tieu_de']}: {(c['tom_tat'] or '')[:500]}" for c in comms]
    extra = (MP.LOCAL_EXTRA_HEADER + "Thực thể:\n" + "\n".join(_cat(dong_tt, int(toi_da * 0.35)))
             + "\nQuan hệ:\n" + "\n".join(_cat(dong_qh, int(toi_da * 0.35)))
             + "\nBáo cáo cộng đồng:\n" + "\n".join(_cat(dong_cd, int(toi_da * 0.3))) + "\n")
    out_units = [graph_rag._serialize_unit(u, {"origin": u["origin"], "score": u["score"], "via": u["via"],
                                               "sua_doi": [], "cited": False}) for u in units]
    graph_ctx = {
        "thuc_the": [{"id": e["id"], "ten": e["ten"], "loai": e["loai"], "mo_ta": e["mo_ta"],
                      "vai_tro": "khop" if e["id"] in seed_ids else "lan_can"} for e in seeds + nb_list],
        "quan_he": [{k: r[k] for k in ("nguon", "dich", "mo_ta", "trong_so")} for r in ctx_rels],
        "cong_dong": [{k: c[k] for k in ("id", "cap", "tieu_de", "tom_tat", "muc_do")} for c in comms],
    }
    yield step("context", t0, f"{len(units)} điều khoản, {len(seeds) + len(nb_list)} thực thể, "
               f"{len(ctx_rels)} quan hệ, {len(comms)} cộng đồng", chi_tiet=CT.ct(
        ["Prompt gồm hai phần: các điều khoản (như hai hệ thống còn lại) và phần đồ thị thực thể: mô tả thực thể, "
         "quan hệ (trong nhóm đã chọn trước, ra ngoài sau, trọng số giảm dần) và tóm tắt báo cáo cộng đồng.",
         f"Phần đồ thị giới hạn {toi_da} ký tự: 35% thực thể, 35% quan hệ, 30% cộng đồng."],
        [["Điều khoản", len(units)], ["Thực thể", len(seeds) + len(nb_list)], ["Quan hệ", len(ctx_rels)],
         ["Cộng đồng", len(comms)], ["Độ dài phần đồ thị", f"{len(extra)} ký tự"]],
        [CT.bang("Quan hệ đưa vào prompt", ["Thực thể", "Thực thể", "Trọng số"],
                 [CT.dong([ten.get(r["nguon"], r["nguon"]), ten.get(r["dich"], r["dich"]), CT.so(r.get("trong_so"), 1)],
                          noi_dung=r.get("mo_ta")) for r in ctx_rels])]))
    yield {"type": "context", "question": q, "date": ngay.isoformat(), "units": out_units,
           "graph": _graph_payload(out_units, graph_ctx, tu_tt, []), "notes": graph_rag._notes_out(notes),
           "graph_context": graph_ctx}

    # Sinh câu trả lời (cùng prompt với hai hệ thống còn lại)
    t0 = time.perf_counter()
    user = ""
    if not units and not notes:
        answer_text = graph_rag.NO_CONTEXT_ANSWER
        if stream:
            yield {"type": "token", "text": answer_text}
    else:
        user = prompts.build_user(q, ngay, units, notes, extra)
        if stream:
            parts = []
            for chunk in res.llm.generate_stream(prompts.SYSTEM, user):
                parts.append(chunk)
                yield {"type": "token", "text": chunk}
            answer_text = "".join(parts)
        else:
            answer_text = res.llm.generate(prompts.SYSTEM, user)
    allowed = [u["id"] for u in units]
    citations, unknown = prompts.parse_citations(answer_text, allowed=allowed)
    yield step("generate", t0, f"{len(citations)} trích dẫn hợp lệ" + (f", {len(unknown)} mã lạ" if unknown else ""),
               chi_tiet=CT.sinh(res.cfg, len(prompts.SYSTEM) + len(user) if user else 0, citations, unknown, allowed))
    for u in out_units:
        u["cited"] = u["id"] in citations
    yield done(answer_text, citations=citations, unknown_citations=unknown, units=out_units,
               graph=_graph_payload(out_units, graph_ctx, tu_tt, citations), notes=graph_rag._notes_out(notes),
               retrieved_ids=unit_ids, graph_context=graph_ctx)


def _graph_payload(units: list[dict], gctx: dict, tu_tt: dict[str, str], citations: list[str]) -> dict:
    """Đồ thị cho giao diện: node thực thể (khớp / lân cận) + node điều khoản; cạnh quan hệ và cạnh 'xuất hiện tại'."""
    cited = set(citations)
    nodes = [{"id": "E:" + e["id"], "label": e["ten"][:40], "cap": "ThucThe", "van_ban_id": None,
              "role": "entity" if e["vai_tro"] == "khop" else "entity_nb", "cited": False, "loai": e["loai"]}
             for e in gctx["thuc_the"]]
    have = {e["id"] for e in gctx["thuc_the"]}
    nodes += [{"id": u["id"], "label": prompts.nhan_ngan(u["id"]), "cap": u.get("cap"), "van_ban_id": u.get("van_ban_id"),
               "role": "seed", "cited": u["id"] in cited} for u in units]
    edges = [{"source": "E:" + r["nguon"], "target": "E:" + r["dich"], "type": "LIEN_QUAN"}
             for r in gctx["quan_he"] if r["nguon"] in have and r["dich"] in have]
    edges += [{"source": "E:" + tu_tt[u["id"]], "target": u["id"], "type": "XUAT_HIEN_TAI"}
              for u in units if tu_tt.get(u["id"]) in have]
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------- global search

def _global(res, q, qvec, mc, step, stream, done, store=ms_store):
    t0 = time.perf_counter()
    with res.pg_pool.connection() as conn:
        comms = store.cong_dong_cho_global(conn, qvec, cap=mc.get("global_level", 0),
                                              k=mc.get("global_top_communities", 24))
    yield step("communities", t0, f"{len(comms)} báo cáo cộng đồng cấp {mc.get('global_level', 0)} "
               "(không lọc theo ngày áp dụng)", chi_tiet=CT.ct(
        [f"Lấy báo cáo cộng đồng cấp {mc.get('global_level', 0)} (cấp cao nhất, bao quát nhất).",
         "Xếp theo cosine giữa câu hỏi và tóm tắt báo cáo, nhân hệ số theo mức độ quan trọng: cosine × (0,5 + mức độ/20).",
         "Global search không trích mã điều khoản và không lọc theo ngày áp dụng."],
        [["Số báo cáo lấy", mc.get("global_top_communities", 24)]],
        [CT.bang("Báo cáo được chọn", ["Mã", "Tiêu đề", "Cosine", "Mức độ"],
                 [CT.dong([c["id"], c["tieu_de"], CT.so(c.get("gan"), 3), CT.so(c.get("muc_do"), 1)],
                          noi_dung=c.get("tom_tat")) for c in comms])]))

    t0 = time.perf_counter()
    n = max(1, mc.get("global_batch", 6))
    nhom = [comms[i:i + n] for i in range(0, len(comms), n)]

    def map_mot(ds):
        bc = "\n\n".join(f"[CĐ {c['id']}] {c['bao_cao'][:2500]}" for c in ds)
        try:
            kq = doc_json(res.llm.generate(MP.MAP_SYSTEM, MP.MAP_USER.format(bao_cao=bc, question=q))) or {}
        except Exception:  # noqa: BLE001
            return []
        out = []
        for y in kq.get("y") or []:
            try:
                d = float(y.get("diem", 0))
            except (TypeError, ValueError, AttributeError):
                continue
            if d > 0 and y.get("mo_ta"):
                out.append({"mo_ta": str(y["mo_ta"]), "diem": d})
        return out

    with ThreadPoolExecutor(max_workers=4) as ex:
        y = [p for kq in ex.map(map_mot, nhom) for p in kq]
    y.sort(key=lambda p: -p["diem"])
    y = y[: mc.get("global_top_points", 20)]
    yield step("map", t0, f"{len(nhom)} lượt map → {len(y)} ý có ích", chi_tiet=CT.ct(
        [f"Chia báo cáo thành nhóm {n} báo cáo; mỗi nhóm gọi LLM một lần (chạy song song) để rút các ý trả lời câu hỏi, "
         "mỗi ý có điểm hữu ích 0–100.",
         f"Bỏ ý điểm 0, xếp theo điểm, giữ {mc.get('global_top_points', 20)} ý tốt nhất cho bước reduce."],
        [["Số lượt map", len(nhom)], ["Ý được giữ", len(y)]],
        [CT.bang("Ý rút được", ["Điểm", "Ý"], [CT.dong([CT.so(p["diem"], 0), CT.trich(p["mo_ta"], 140)],
                                                       noi_dung=p["mo_ta"]) for p in y])]))
    cong_dong = [{k: c[k] for k in ("id", "cap", "tieu_de", "tom_tat", "muc_do")} for c in comms]
    yield {"type": "context", "question": q, "units": [], "graph": {"nodes": [], "edges": []}, "notes": [],
           "graph_context": {"thuc_the": [], "quan_he": [], "cong_dong": cong_dong}}

    t0 = time.perf_counter()
    if not y:
        answer_text = "Các báo cáo cộng đồng của đồ thị không có thông tin đủ để trả lời câu hỏi này."
        if stream:
            yield {"type": "token", "text": answer_text}
    else:
        user = MP.REDUCE_USER.format(y="\n".join(f"- ({p['diem']:.0f}) {p['mo_ta']}" for p in y), question=q)
        if stream:
            parts = []
            for chunk in res.llm.generate_stream(MP.REDUCE_SYSTEM, user):
                parts.append(chunk)
                yield {"type": "token", "text": chunk}
            answer_text = "".join(parts)
        else:
            answer_text = res.llm.generate(MP.REDUCE_SYSTEM, user)
    yield step("reduce", t0, f"tổng hợp từ {len(y)} ý", chi_tiet=CT.ct(
        ["LLM nhận các ý đã chọn (kèm điểm) và viết câu trả lời tổng hợp."],
        [["Mô hình", res.cfg["llm"]["model"]], ["Số ý", len(y)]]))
    yield done(answer_text, graph_context={"thuc_the": [], "quan_he": [], "cong_dong": cong_dong})


def answer(res, question: str, ngay: date | None = None, history: list[dict] | None = None,
           che_do: str = "local", hops: int | None = None, use_temporal_filter: bool = True, **_) -> dict:
    out: dict = {}
    for ev in run(res, question, ngay=ngay, history=history, che_do=che_do, hops=hops,
                  use_temporal_filter=use_temporal_filter):
        if ev["type"] == "done":
            out = {k: v for k, v in ev.items() if k != "type"}
    return out
