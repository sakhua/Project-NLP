"""GraphRAG đề xuất. Phụ trách: TV1.

0. (Hội thoại) Viết lại câu hỏi tiếp nối thành câu hỏi đầy đủ (pipeline.conversation).
1. Seed: BM25 (res.bm25) + vector (res.embedder + postgres.vector_search), gộp RRF, lọc theo ngày áp dụng,
   rerank top_k_rerank ứng viên (retrieval.rerank.rerank, mô hình qua OpenRouter), giữ top_k_final.
   Kết quả tìm kiếm là vid (mã phiên bản) → đổi sang mã đơn vị bằng ids.base_id, bỏ trùng, giữ thứ tự.
2. Mở rộng đồ thị trên mã đơn vị (neo4j_store.expand_paths): THAM_CHIEU, HUONG_DAN, THUOC, cả hai chiều.
   Ưu tiên: ít bước hơn → THAM_CHIEU → HUONG_DAN → đơn vị cha → đơn vị con (chỉ của 3 seed đầu) → seed xếp trên.
3. Lọc theo ngày áp dụng: postgres.fetch_valid(mã đơn vị, ngay) trả đúng phiên bản có hiệu lực
   (thiết kế phiên bản: docs/thiet_ke_do_thi.md). Ứng viên khớp câu hỏi nhưng chưa/hết hiệu lực được ghi chú
   riêng cho LLM (prompts.format_notes) để trả lời "chưa có hiệu lực từ ngày …".
4. Ghép ngữ cảnh (prompts.build_user) và gọi LLM (llm.model); tách trích dẫn (prompts.parse_citations).

Cùng một pipeline dùng cho môn NLP (answer(): chạy đánh giá) và backend (run(): phát từng bước cho giao diện).
Các cờ dùng cho ablation: use_amendments, use_references, use_temporal_filter, hops.
"""
from __future__ import annotations

import re
import time
from collections.abc import Iterator
from datetime import date

from graphrag.common.ids import base_id
from graphrag.pipeline import intent as intent_mod
from graphrag.pipeline import prompts
from graphrag.pipeline.conversation import rewrite_question
from graphrag.retrieval.fusion import rrf
from graphrag.retrieval.query_expansion import expand as expand_query
from graphrag.retrieval.rerank import rerank
from graphrag.storage import neo4j_store, postgres

NO_CONTEXT_ANSWER = "Không tìm thấy quy định áp dụng trong các văn bản được cung cấp."

# Nhãn các bước hiển thị trên giao diện (tab "Quy trình")
STEPS = {
    "intent": "Phân loại câu hỏi",
    "rewrite": "Hiểu câu hỏi theo ngữ cảnh hội thoại",
    "search": "Tìm kiếm lai BM25 + vector, gộp RRF",
    "rerank": "Lọc theo ngày áp dụng và xếp hạng lại",
    "graph": "Mở rộng trên đồ thị tri thức",
    "context": "Ghép ngữ cảnh theo phiên bản hiệu lực",
    "generate": "Sinh câu trả lời có trích dẫn",
}

# Độ ưu tiên khi chọn đơn vị mở rộng (số nhỏ = ưu tiên trước)
EDGE_PRIORITY = {"THAM_CHIEU": 0, "HUONG_DAN": 1, "THUOC_CHA": 2, "THUOC_CON": 3}
MAX_SEEDS_WITH_CHILDREN = 3


def _unique(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _text(u: dict) -> str:
    return f"{u.get('ngu_canh') or ''}\n{u['noi_dung']}".strip()


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


# Câu lệnh sửa đổi trong văn bản sửa đổi ("Sửa đổi, bổ sung điểm m khoản 3 như sau: …"): nội dung mới đã nằm trong
# phiên bản của điều khoản bị sửa, nên bỏ các câu lệnh này khỏi ngữ cảnh để không trùng và không gây nhiễu.
_AMEND_INSTR = re.compile(r"^\s*(Sửa đổi|Bổ sung|Bãi bỏ|Thay thế|Thay cụm từ|Thay từ|Bỏ cụm từ|Bỏ từ)", re.IGNORECASE)


def _is_amend_instruction(u: dict) -> bool:
    return bool(_AMEND_INSTR.match(u.get("noi_dung") or ""))


def _validity_notes(conn, ranked_ids: list[str], valid_ids: set[str], ngay: date, limit: int = 4) -> list[dict]:
    """Ứng viên xếp hạng cao nhưng không có phiên bản hiệu lực tại `ngay`: chưa có hiệu lực hoặc đã hết hiệu lực."""
    missing = [i for i in ranked_ids if i not in valid_ids]
    if not missing:
        return []
    by: dict[str, list[dict]] = {}
    for r in postgres.get_units(conn, missing):
        by.setdefault(r["id"], []).append(r)
    notes = []
    for i in missing:
        vs = by.get(i)
        if not vs or vs[0]["cap"] == "Chuong" or _is_amend_instruction(vs[-1]):
            continue
        sau = [v for v in vs if v["hieu_luc_tu"] > ngay]
        if sau:
            notes.append({"id": i, "trang_thai": "chua_hieu_luc", "ngay": sau[0]["hieu_luc_tu"],
                          "noi_dung": sau[0]["noi_dung"][:400]})
        else:
            den = max((v["hieu_luc_den"] for v in vs if v["hieu_luc_den"]), default=None)
            if den is None:
                continue
            notes.append({"id": i, "trang_thai": "het_hieu_luc", "ngay": den, "noi_dung": vs[-1]["noi_dung"][:400]})
        if len(notes) >= limit:
            break
    return notes


def _edge_kind(path: dict) -> str:
    first = path["rels"][0]
    if first["type"] != "THUOC":
        return first["type"]
    return "THUOC_CHA" if first["src"] == path["seed"] else "THUOC_CON"


def _select_expansion(paths: list[dict], seed_ids: list[str], max_expand: int) -> dict[str, dict]:
    """Chọn tối đa `max_expand` đơn vị mở rộng; trả về {mã: đường đi tốt nhất (thêm khóa 'kind')}."""
    rank = {s: i for i, s in enumerate(seed_ids)}
    best: dict[str, tuple] = {}
    for p in paths:
        if p["id"] in rank or p["seed"] not in rank or not p.get("rels"):
            continue
        kind = _edge_kind(p)
        if kind == "THUOC_CON" and rank[p["seed"]] >= MAX_SEEDS_WITH_CHILDREN:
            continue
        key = (p["hops"], EDGE_PRIORITY.get(kind, 9), rank[p["seed"]], p["id"])
        if p["id"] not in best or key < best[p["id"]][0]:
            best[p["id"]] = (key, {**p, "kind": kind})
    chosen = sorted(best.values(), key=lambda kv: kv[0])[:max_expand]
    return {p["id"]: p for _, p in chosen}


def _graph_payload(units: list[dict], chosen: dict[str, dict], citations: list[str]) -> dict:
    """Đồ thị con cho giao diện: node = đơn vị trong ngữ cảnh (+ node trung gian), cạnh = đường đi đã dùng."""
    cited = set(citations)
    nodes = {u["id"]: {"id": u["id"], "label": prompts.nhan_ngan(u["id"]), "cap": u.get("cap"),
                       "van_ban_id": u.get("van_ban_id"), "role": u["origin"], "cited": u["id"] in cited}
             for u in units}
    edges, seen = [], set()
    for uid, p in chosen.items():
        if uid not in nodes:
            continue
        for r in p["rels"]:
            for end in (r["src"], r["dst"]):
                if end not in nodes:
                    nodes[end] = {"id": end, "label": prompts.nhan_ngan(end), "cap": None, "van_ban_id": None,
                                  "role": "path", "cited": False}
            k = (r["src"], r["type"], r["dst"])
            if k not in seen:
                seen.add(k)
                edges.append({"source": r["src"], "target": r["dst"], "type": r["type"]})
    return {"nodes": list(nodes.values()), "edges": edges}


def _serialize_unit(u: dict, extra: dict) -> dict:
    keys = ("vid", "id", "van_ban_id", "cap", "tieu_de", "noi_dung", "ngu_canh", "hieu_luc_tu", "hieu_luc_den",
            "nguon_sua_doi", "loai_phien_ban")
    out = {k: u.get(k) for k in keys}
    out["ten"] = prompts.ten_dieu_khoan(u["id"], prompts._ten_van_ban(u))
    out["nhan"] = prompts.nhan_ngan(u["id"])
    out["nguon_ten"] = prompts.ten_dieu_khoan(u["nguon_sua_doi"]) if u.get("nguon_sua_doi") else None
    out.update(extra)
    return out


def _notes_out(notes: list[dict]) -> list[dict]:
    return [{**n, "ten": prompts.ten_dieu_khoan(n["id"]), "ngay": n["ngay"].isoformat()} for n in notes]


def run(res, question: str, ngay: date | None = None, history: list[dict] | None = None,
        hops: int | None = None, use_amendments: bool = True, use_references: bool = True,
        use_temporal_filter: bool = True, stream: bool = False) -> Iterator[dict]:
    """Chạy pipeline và phát sự kiện theo từng bước (giao diện hiện tiến trình):

      {"type": "step", "key", "label", "ms", "detail"}               sau mỗi bước
      {"type": "context", "question", "units", "graph", "notes"}     trước khi sinh câu trả lời
      {"type": "token", "text"}                                      từng đoạn chữ (chỉ khi stream=True)
      {"type": "done", **kết quả}                                    kết quả cuối, cùng dạng với answer()
    """
    cfg = res.cfg
    rc, gc = cfg["retrieval"], cfg.get("graph", {})
    ngay = ngay or date.today()
    hops = hops if hops is not None else gc.get("hops", 1)
    edge_types = [e for e in gc.get("edge_types", ["THAM_CHIEU", "HUONG_DAN", "THUOC"])
                  if use_references or e == "THUOC"]
    t_start = time.perf_counter()
    steps: list[dict] = []

    def step(key: str, t0: float, detail: str, **data) -> dict:
        ev = {"type": "step", "key": key, "label": STEPS[key], "ms": _ms(t0), "detail": detail, **data}
        steps.append({k: v for k, v in ev.items() if k != "type"})
        return ev

    # 0a. Câu xã giao (chào, cảm ơn…) hoặc có từ khóa giao thông: nhận ra ngay bằng luật trên câu gốc
    t0 = time.perf_counter()
    label, how = intent_mod.classify(question, llm=None)
    q = question.strip()
    # 0b. Hội thoại: viết lại câu tiếp nối thành câu đầy đủ (vd. "còn xe máy thì sao?")
    if label == intent_mod.LUAT and history:
        t1 = time.perf_counter()
        q = rewrite_question(res.llm, history, question, cfg.get("conversation", {}).get("history_turns", 3))
        yield step("rewrite", t1, "Câu hỏi đã đầy đủ" if q == question.strip() else f"Hiểu là: {q}", question=q)
    # 0c. Chưa chắc (không có từ khóa): phân loại câu đã viết lại, cần thì hỏi LLM
    if label == intent_mod.LUAT and how != "luật":
        t0 = time.perf_counter()
        label, how = intent_mod.classify(q, llm=res.llm if cfg.get("intent", {}).get("use_llm", True) else None)
    yield step("intent", t0, f"{intent_mod.LABELS[label]} (xác định bằng {how})", intent=label)

    if label != intent_mod.LUAT:          # không tra cứu: trả lời mẫu
        answer_text = intent_mod.REPLIES[label]
        if stream:
            for part in re.split(r"(\s+)", answer_text):
                if part:
                    yield {"type": "token", "text": part}
        yield {
            "type": "done", "intent": label,
            "question": question, "question_rewritten": q if q != question.strip() else None,
            "date": ngay.isoformat(), "answer": answer_text, "citations": [], "unknown_citations": [],
            "units": [], "graph": {"nodes": [], "edges": []}, "notes": [], "retrieved_ids": [], "steps": steps,
            "latency_s": round(time.perf_counter() - t_start, 3),
        }
        return

    # 1a. Tìm kiếm lai
    t0 = time.perf_counter()
    q_bm25 = expand_query(q) if rc.get("query_expansion", True) else q
    bm25_vids = [vid for vid, _ in res.bm25.search(q_bm25, k=rc["top_k_bm25"])]
    dense_vids, dense_err = [], None
    try:
        qvec = res.embedder.encode_queries([q])[0]
        with res.pg_pool.connection() as conn:
            dense_vids = [vid for vid, _ in postgres.vector_search(conn, qvec, k=rc["top_k_dense"])]
    except Exception as e:  # noqa: BLE001 – mất embedding vẫn trả lời được bằng BM25
        dense_err = type(e).__name__
    fused = rrf([_unique(base_id(v) for v in bm25_vids), _unique(base_id(v) for v in dense_vids)], k=rc["rrf_k"])
    cand_ids = [i for i, _ in fused][: rc["top_k_rerank"]]
    yield step("search", t0, f"BM25 {len(bm25_vids)} · vector {len(dense_vids)}"
               + (f" (lỗi {dense_err})" if dense_err else "") + f" → {len(cand_ids)} ứng viên",
               bm25=len(bm25_vids), dense=len(dense_vids))

    # 1b. Lọc theo ngày + rerank
    t0 = time.perf_counter()
    with res.pg_pool.connection() as conn:
        if use_temporal_filter:
            valid = {r["id"]: r for r in postgres.fetch_valid(conn, cand_ids, ngay)}
            notes = _validity_notes(conn, cand_ids[:10], set(valid), ngay)
        else:
            valid, notes = postgres.latest_versions(conn, cand_ids), []
    pool = [(i, _text(valid[i])) for i in cand_ids
            if i in valid and valid[i]["cap"] != "Chuong" and not _is_amend_instruction(valid[i])]
    rerank_note = ""
    try:
        ranked = rerank(cfg, q, pool, top_n=rc["top_k_final"])
    except Exception as e:  # noqa: BLE001 – dịch vụ rerank lỗi: dùng thứ tự RRF
        ranked = [(i, 0.0) for i, _ in pool[: rc["top_k_final"]]]
        rerank_note = f" (rerank lỗi {type(e).__name__}, dùng thứ tự RRF)"
    seed_ids = [i for i, _ in ranked]
    seed_score = dict(ranked)
    yield step("rerank", t0, f"{len(pool)}/{len(cand_ids)} còn hiệu lực ngày {prompts.ngay_vn(ngay)} → "
               f"giữ {len(seed_ids)}" + (f"; {len(notes)} quy định chưa/hết hiệu lực" if notes else "") + rerank_note,
               seeds=seed_ids)

    # 2. Mở rộng đồ thị
    t0 = time.perf_counter()
    chosen: dict[str, dict] = {}
    graph_note = ""
    if hops and seed_ids and edge_types:
        try:
            paths = neo4j_store.expand_paths(res.neo4j, seed_ids, hops, edge_types)
            chosen = _select_expansion(paths, seed_ids, gc.get("max_expand", 30))
        except Exception as e:  # noqa: BLE001 – Neo4j tắt: vẫn trả lời bằng seed
            graph_note = f" (Neo4j lỗi {type(e).__name__}, bỏ qua bước này)"
    exp_rows: dict[str, dict] = {}
    if chosen:
        with res.pg_pool.connection() as conn:
            ids = list(chosen)
            exp_rows = ({r["id"]: r for r in postgres.fetch_valid(conn, ids, ngay)} if use_temporal_filter
                        else postgres.latest_versions(conn, ids))
    exp_rows = {i: r for i, r in exp_rows.items()
                if r["cap"] != "Chuong" and len(r["noi_dung"] or "") >= 15 and not _is_amend_instruction(r)}
    chosen = {i: p for i, p in chosen.items() if i in exp_rows}
    by_kind: dict[str, int] = {}
    for p in chosen.values():
        by_kind[p["kind"]] = by_kind.get(p["kind"], 0) + 1
    names = {"THAM_CHIEU": "dẫn chiếu", "HUONG_DAN": "hướng dẫn", "THUOC_CHA": "cha", "THUOC_CON": "con"}
    kinds = ", ".join(f"{names.get(k, k)} {n}" for k, n in by_kind.items())
    yield step("graph", t0, f"+{len(chosen)} điều khoản" + (f" ({kinds})" if kinds else "") + graph_note,
               added=len(chosen), by_kind=by_kind)

    # 3. Ghép ngữ cảnh
    t0 = time.perf_counter()
    units: list[dict] = []
    for i in seed_ids:
        units.append({**valid[i], "origin": "seed", "score": round(float(seed_score.get(i) or 0.0), 4), "via": None})
    for i, p in chosen.items():
        units.append({**exp_rows[i], "origin": "graph", "score": None,
                      "via": {"type": p["rels"][0]["type"], "kind": p["kind"], "from": p["seed"], "hops": p["hops"]}})
    if not use_amendments:
        units = [{**u, "nguon_sua_doi": None} for u in units]
    lich_su: dict[str, list[dict]] = {}
    if units and use_amendments:
        try:
            for a in neo4j_store.amended_by(res.neo4j, [u["id"] for u in units]):
                lich_su.setdefault(a["id"], []).append(
                    {"loai": a["loai"], "nguon": a["nguon"], "nguon_ten": prompts.ten_dieu_khoan(a["nguon"]),
                     "ngay_hieu_luc": a["ngay_hieu_luc"]})
        except Exception:  # noqa: BLE001
            pass
    out_units = [_serialize_unit(u, {"origin": u["origin"], "score": u["score"], "via": u["via"],
                                     "sua_doi": lich_su.get(u["id"], []), "cited": False}) for u in units]
    yield step("context", t0, f"{len(units)} điều khoản ({len(seed_ids)} tìm trực tiếp, {len(chosen)} từ đồ thị)")
    yield {"type": "context", "question": q, "date": ngay.isoformat(), "units": out_units,
           "graph": _graph_payload(out_units, chosen, []), "notes": _notes_out(notes)}

    # 4. Sinh câu trả lời
    t0 = time.perf_counter()
    if not units and not notes:
        answer_text = NO_CONTEXT_ANSWER
        if stream:
            yield {"type": "token", "text": answer_text}
    else:
        user = prompts.build_user(q, ngay, units, notes)
        if stream:
            parts = []
            for chunk in res.llm.generate_stream(prompts.SYSTEM, user):
                parts.append(chunk)
                yield {"type": "token", "text": chunk}
            answer_text = "".join(parts)
        else:
            answer_text = res.llm.generate(prompts.SYSTEM, user)
    citations, unknown = prompts.parse_citations(answer_text, allowed=[u["id"] for u in units])
    yield step("generate", t0, f"{len(citations)} trích dẫn hợp lệ" + (f", {len(unknown)} mã lạ" if unknown else ""))

    for u in out_units:
        u["cited"] = u["id"] in citations
    yield {
        "type": "done", "intent": intent_mod.LUAT,
        "question": question, "question_rewritten": q if q != question.strip() else None,
        "date": ngay.isoformat(), "answer": answer_text, "citations": citations, "unknown_citations": unknown,
        "units": out_units, "graph": _graph_payload(out_units, chosen, citations), "notes": _notes_out(notes),
        "retrieved_ids": seed_ids + list(chosen), "steps": steps,
        "latency_s": round(time.perf_counter() - t_start, 3),
    }


def answer(res, question: str, ngay: date | None = None, hops: int | None = None,
           use_amendments: bool = True, use_references: bool = True,
           use_temporal_filter: bool = True, history: list[dict] | None = None) -> dict:
    """res: graphrag.resources.Resources.

    Trả về {'answer': str, 'citations': [mã đơn vị], 'units': [dict phiên bản trong ngữ cảnh],
            'retrieved_ids': [mã đơn vị theo thứ tự xếp hạng], 'latency_s': float, ...}
    Trích dẫn và retrieved_ids luôn là MÃ ĐƠN VỊ (không có '@ngày') để so với gold.
    """
    result: dict = {}
    for ev in run(res, question, ngay=ngay, history=history, hops=hops, use_amendments=use_amendments,
                  use_references=use_references, use_temporal_filter=use_temporal_filter, stream=False):
        if ev["type"] == "done":
            result = {k: v for k, v in ev.items() if k != "type"}
    return result
