"""Dựng chỉ mục theo GraphRAG GỐC của Microsoft (microsoft/graphrag 3.x, cấu hình mặc định).

Khác bản gốc DUY NHẤT ở bước chia chunk: mỗi phiên bản Điều/Khoản/Điểm (kèm câu dẫn của khoản) là một text unit,
thay cho đoạn 1.200 token chồng 100 token, để kết quả truy xuất so được với mã điều khoản gold.
Các bước còn lại làm như bản gốc:
  1. extract_graph: prompt GRAPH_EXTRACTION_PROMPT nguyên văn, 4 loại thực thể mặc định (organization, person, geo,
     event), đầu ra dạng ("entity"<|>…)##…<|COMPLETE|>, gleaning 1 vòng (hội thoại nhiều lượt với CONTINUE_PROMPT).
     Thực thể gộp theo tên (viết hoa), quan hệ gộp theo cặp, trọng số cộng dồn; bỏ quan hệ có đầu mút không phải thực thể.
  2. summarize_descriptions: thực thể/quan hệ có từ 2 mô tả khác nhau thì LLM tóm tắt (SUMMARIZE_PROMPT, tối đa 500 từ).
  3. cluster_graph: Leiden phân cấp trên thành phần liên thông lớn nhất (use_lcc), cộng đồng > 10 thực thể chia tiếp.
  4. community_reports: COMMUNITY_REPORT_PROMPT nguyên văn, ngữ cảnh là bảng Entities/Relationships (CSV) xếp theo bậc,
     tối đa 8.000 token; cộng đồng quá lớn dùng báo cáo của cộng đồng con. Đầu ra JSON title/summary/rating/findings.
  5. Embedding "tên:mô tả" của thực thể (bge-m3, cùng embedder với hai hệ thống còn lại).
Mọi lượt gọi LLM được lưu đệm (ix.Cache) nên chạy lại không tốn tiền phần đã xong.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
from collections import Counter, defaultdict

from graphrag.ms_graphrag import indexing as ix
from graphrag.ms_graphrag import prompts_goc as PG

TUPLE_DELIMITER = "<|>"
RECORD_DELIMITER = "##"
COMPLETION_DELIMITER = "<|COMPLETE|>"

try:   # đếm token như bản gốc (tiktoken); không cài thì ước lượng theo số ký tự
    import tiktoken

    _ENC = tiktoken.get_encoding("o200k_base")

    def so_token(text: str) -> int:
        return len(_ENC.encode(text or "", disallowed_special=()))
except Exception:  # noqa: BLE001
    def so_token(text: str) -> int:
        return (len(text or "") + 2) // 3


# ---------------------------------------------------------------- 0. text unit

def text_units(versions: list[dict], van_ban: list[str] | None = None, gioi_han: int | None = None) -> list[dict]:
    """Mỗi phiên bản Điều/Khoản/Điểm có nội dung là một text unit; ma_ngan = id ngắn (human_readable_id) 1, 2, 3…
    dùng trong ngữ cảnh "Sources" và trong trích dẫn [Data: Sources (…)] của câu trả lời."""
    units = ix.don_vi_van_ban(versions, van_ban, gioi_han)
    for i, u in enumerate(units, 1):
        u["ma_ngan"] = i
    return units


# ---------------------------------------------------------------- 1. extract_graph

def _clean_str(s: str) -> str:
    """Như graphrag.index.utils.string.clean_str: bỏ mã HTML, ký tự điều khiển, khoảng trắng và dấu nháy hai đầu."""
    s = html.unescape(str(s).strip())
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", s)
    return s.strip().strip('"').strip()


def goi_trich_xuat(llm, text: str, entity_types: list[str], max_gleanings: int = 1) -> str:
    """Giống GraphExtractor._process_document: một lượt chính rồi gleaning trong cùng hội thoại."""
    msgs = [{"role": "user", "content": PG.GRAPH_EXTRACTION_PROMPT.format(
        entity_types=",".join(entity_types), input_text=text)}]
    out = llm.generate_messages(msgs)
    msgs.append({"role": "assistant", "content": out})
    results = out
    for i in range(max_gleanings):
        msgs.append({"role": "user", "content": PG.CONTINUE_PROMPT})
        r = llm.generate_messages(msgs)
        msgs.append({"role": "assistant", "content": r})
        results += r
        if i >= max_gleanings - 1:
            break
        msgs.append({"role": "user", "content": PG.LOOP_PROMPT})
        if llm.generate_messages(msgs).strip() != "Y":
            break
    return results


def doc_ket_qua(raw: str) -> dict:
    """Đọc chuỗi ("entity"<|>TÊN<|>LOẠI<|>mô tả)##("relationship"<|>A<|>B<|>mô tả<|>độ mạnh)… như _process_result.
    Trả về cùng dạng với bản đã chỉnh để dùng lại hàm gộp: {"thuc_the": […], "quan_he": […]}."""
    tt, qh = [], []
    for rec in (raw or "").replace(COMPLETION_DELIMITER, RECORD_DELIMITER).split(RECORD_DELIMITER):
        rec = re.sub(r"^\(|\)$", "", rec.strip())
        if not rec:
            continue
        a = rec.split(TUPLE_DELIMITER)
        if a[0].strip() == '"entity"' and len(a) >= 4:
            ten = _clean_str(a[1].upper())
            if ten:
                tt.append({"ten": ten, "loai": _clean_str(a[2].upper()), "mo_ta": _clean_str(a[3])})
        elif a[0].strip() == '"relationship"' and len(a) >= 5:
            try:
                w = float(_clean_str(a[-1]))
            except ValueError:
                w = 1.0
            nguon, dich = _clean_str(a[1].upper()), _clean_str(a[2].upper())
            if nguon and dich:
                qh.append({"nguon": nguon, "dich": dich, "mo_ta": _clean_str(a[3]), "do_manh": w})
    return {"thuc_the": tt, "quan_he": qh}


def trich_xuat(llm, units: list[dict], cache: ix.Cache, entity_types: list[str], max_gleanings: int = 1,
               workers: int = 8, tien_do=None) -> tuple[dict[str, dict], list[str]]:
    """Cache lưu chuỗi thô của LLM theo vid (đọc lại được nếu đổi bộ đọc). Lỗi tài khoản → LoiKhongTheTiepTuc."""
    loi: list[str] = []
    dung: list[str] = []
    can = [u for u in units if u["vid"] not in cache]

    def mot(u):
        if dung:
            return
        try:
            cache.put(u["vid"], goi_trich_xuat(llm, u["text"], entity_types, max_gleanings))
        except Exception as e:  # noqa: BLE001
            if ix._LOI_TAI_KHOAN.search(str(e)):
                dung.append(str(e)[:300])
                return
            loi.append(f"{u['vid']}: {type(e).__name__}: {str(e)[:120]}")

    ix.chay_song_song(can, mot, workers, tien_do)
    if dung:
        raise ix.LoiKhongTheTiepTuc(dung[0])
    return {u["vid"]: doc_ket_qua(cache.get(u["vid"])) for u in units if u["vid"] in cache}, loi


def gop(ket_qua: dict[str, dict], vid_to_id: dict[str, str]) -> tuple[dict[str, dict], dict[tuple, dict]]:
    """Gộp như bản gốc rồi bỏ quan hệ mồ côi (filter_orphan_relationships)."""
    tt, qh = ix.gop(ket_qua, vid_to_id)
    qh = {k: d for k, d in qh.items() if k[0] in tt and k[1] in tt}
    for d in list(tt.values()) + list(qh.values()):
        d["mo_ta"] = sorted(set(d["mo_ta"]))       # bản gốc: sorted(set(descriptions))
    return tt, qh


# ---------------------------------------------------------------- 2. summarize_descriptions

def tom_tat(llm, tt: dict[str, dict], qh: dict[tuple, dict], cache: ix.Cache, max_length: int = 500,
            workers: int = 8, tien_do=None) -> list[str]:
    """Gán d['mo_ta_tong']: 0 mô tả → '', 1 mô tả → giữ nguyên, ≥ 2 → LLM tóm tắt (SUMMARIZE_PROMPT)."""
    viec = []
    for k, d in tt.items():
        viec.append((d["ten"], d))
    for (a, b), d in qh.items():
        viec.append((sorted([tt[a]["ten"], tt[b]["ten"]]), d))
    can = []
    for ten, d in viec:
        if len(d["mo_ta"]) <= 1:
            d["mo_ta_tong"] = d["mo_ta"][0] if d["mo_ta"] else ""
            continue
        key = "S:" + hashlib.sha1(json.dumps([ten, d["mo_ta"]], ensure_ascii=False).encode()).hexdigest()[:20]
        if key in cache:
            d["mo_ta_tong"] = cache.get(key)
        else:
            can.append((key, ten, d))
    loi: list[str] = []

    def mot(item):
        key, ten, d = item
        prompt = PG.SUMMARIZE_PROMPT.format(entity_name=json.dumps(ten, ensure_ascii=False),
                                            description_list=json.dumps(sorted(d["mo_ta"]), ensure_ascii=False),
                                            max_length=max_length)
        try:
            out = llm.generate_messages([{"role": "user", "content": prompt}]).strip()
            cache.put(key, out)
            d["mo_ta_tong"] = out
        except Exception as e:  # noqa: BLE001
            d["mo_ta_tong"] = " ".join(d["mo_ta"])
            loi.append(f"{key}: {type(e).__name__}")

    ix.chay_song_song(can, mot, workers, tien_do)
    return loi


# ---------------------------------------------------------------- 3. cluster_graph (Leiden phân cấp, use_lcc)

def cong_dong(tt: dict[str, dict], qh: dict[tuple, dict], max_cluster_size: int = 10,
              max_level: int = 10) -> tuple[list[dict], str]:
    import networkx as nx

    G = nx.Graph()
    G.add_nodes_from(tt)
    G.add_edges_from(k for k in qh)
    if G.number_of_nodes() == 0:
        return [], "leiden"
    lcc = max(nx.connected_components(G), key=len)
    tt_lcc = {k: v for k, v in tt.items() if k in lcc}
    qh_lcc = {k: v for k, v in qh.items() if k[0] in lcc and k[1] in lcc}
    return ix.cong_dong(tt_lcc, qh_lcc, max_cluster_size, max_level, co_toi_thieu=1)


# ---------------------------------------------------------------- 4. community_reports

def gan_bac(tt: dict[str, dict], qh: dict[tuple, dict]) -> None:
    """degree của thực thể, combined_degree của quan hệ, id ngắn (human_readable_id) cho cả hai."""
    bac = Counter()
    for a, b in qh:
        bac[a] += 1
        bac[b] += 1
    for i, (k, d) in enumerate(sorted(tt.items()), 1):
        d["bac"], d["ma_ngan"] = bac[k], i
    for i, (k, d) in enumerate(sorted(qh.items()), 1):
        d["bac_ket_hop"], d["ma_ngan"] = bac[k[0]] + bac[k[1]], i


def _csv(rows: list[list]) -> str:
    f = io.StringIO()
    csv.writer(f, lineterminator="\n").writerows(rows)
    return f.getvalue()


def ngu_canh_cong_dong(c: dict, tt: dict, qh_theo_tt: dict, bao_cao_con: list[dict], toi_da_token: int) -> str:
    """Như sort_context: quan hệ xếp theo combined_degree giảm dần, thêm dần quan hệ và hai đầu mút cho tới khi hết
    ngân sách token; thực thể không có quan hệ nằm sau. Quá ngân sách thì đặt báo cáo cộng đồng con lên đầu."""
    tv = set(c["thanh_vien"])
    rels = sorted({k for e in tv for k in qh_theo_tt.get(e, ()) if k[0] in tv and k[1] in tv},
                  key=lambda k: -qh_theo_tt["__d"][k]["bac_ket_hop"])

    def chuoi(ents: list[str], rs: list[tuple], con: list[dict]) -> str:
        parts = []
        if con:
            parts.append("----Reports-----\n" + _csv([["community", "full_content"]]
                                                     + [[b["id"], b["noi_dung"]] for b in con]))
        if ents:
            parts.append("-----Entities-----\n" + _csv(
                [["short_id", "title", "description", "degree"]]
                + [[tt[e]["ma_ngan"], tt[e]["ten"], tt[e].get("mo_ta_tong", ""), tt[e]["bac"]] for e in ents]))
        if rs:
            parts.append("-----Relationships-----\n" + _csv(
                [["short_id", "source", "target", "description", "combined_degree"]]
                + [[qh_theo_tt["__d"][k]["ma_ngan"], tt[k[0]]["ten"], tt[k[1]]["ten"],
                    qh_theo_tt["__d"][k].get("mo_ta_tong", ""), qh_theo_tt["__d"][k]["bac_ket_hop"]] for k in rs]))
        return "\n\n".join(parts)

    day_du = chuoi(sorted(tv, key=lambda e: -tt[e]["bac"]), rels, [])
    if so_token(day_du) <= toi_da_token:
        return day_du
    con = []
    if bao_cao_con:            # cộng đồng quá lớn: dùng báo cáo cộng đồng con (tối đa nửa ngân sách)
        for b in sorted(bao_cao_con, key=lambda b: -so_token(b["noi_dung"])):
            if so_token(chuoi([], [], con + [b])) > toi_da_token // 2:
                break
            con.append(b)
    ents, rs, text = [], [], chuoi([], [], con)
    for k in rels:
        e2 = ents + [e for e in k if e not in ents]
        t2 = chuoi(e2, rs + [k], con)
        if so_token(t2) > toi_da_token:
            break
        ents, rs, text = e2, rs + [k], t2
    return text


def doc_bao_cao(raw: str) -> dict | None:
    kq = ix.doc_json(raw)
    if not kq or not kq.get("title"):
        return None
    try:
        rating = float(kq.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0.0
    return {"tieu_de": str(kq["title"]), "tom_tat": str(kq.get("summary", "")), "muc_do": rating,
            "ly_do_muc_do": str(kq.get("rating_explanation", "")),
            "phat_hien": [{"tom_tat": str(f.get("summary", "")), "giai_thich": str(f.get("explanation", ""))}
                          for f in kq.get("findings") or [] if isinstance(f, dict)]}


def bao_cao_cong_dong(llm, comms: list[dict], tt: dict, qh: dict, cache: ix.Cache, max_length: int = 2000,
                      max_input_tokens: int = 8000, workers: int = 8, tien_do=None) -> list[str]:
    qh_theo_tt: dict = defaultdict(list)
    for k in qh:
        qh_theo_tt[k[0]].append(k)
        qh_theo_tt[k[1]].append(k)
    qh_theo_tt["__d"] = qh
    theo_id = {c["id"]: c for c in comms}
    con_cua: dict[str, list[str]] = defaultdict(list)
    for c in comms:
        if c["cha"]:
            con_cua[c["cha"]].append(c["id"])
    loi: list[str] = []
    xong = [0]

    def mot(c):
        con = [{"id": i, "noi_dung": ix.van_ban_bao_cao(theo_id[i])} for i in con_cua.get(c["id"], [])
               if theo_id[i].get("bao_cao")]
        ctx = ngu_canh_cong_dong(c, tt, qh_theo_tt, con, max_input_tokens)
        key = "R:" + hashlib.sha1(ctx.encode("utf-8")).hexdigest()[:20]
        if key in cache:
            c["bao_cao"] = cache.get(key)
        else:
            try:
                raw = llm.generate_messages([{"role": "user", "content": PG.COMMUNITY_REPORT_PROMPT.format(
                    input_text=ctx, max_report_length=max_length)}])
                kq = doc_bao_cao(raw)
                if kq is None:
                    raise ValueError("báo cáo không phải JSON hợp lệ")
                cache.put(key, kq)
                c["bao_cao"] = kq
            except Exception as e:  # noqa: BLE001
                loi.append(f"{c['id']}: {type(e).__name__}: {str(e)[:100]}")
        xong[0] += 1
        if tien_do:
            tien_do(xong[0], len(comms))

    for cap in sorted({c["cap"] for c in comms}, reverse=True):     # cấp sâu trước để cấp trên dùng báo cáo con
        ix.chay_song_song([c for c in comms if c["cap"] == cap], mot, workers)
    return loi


# ---------------------------------------------------------------- 5. lưu

def luu_ket_qua(thu_muc, units: list[dict], tt: dict, qh: dict, comms: list[dict], thuat_toan: str) -> None:
    ix.ghi_jsonl(thu_muc / "text_units.jsonl", [{"ma_ngan": u["ma_ngan"], "vid": u["vid"], "id": u["id"]}
                                               for u in units])
    ix.ghi_jsonl(thu_muc / "thuc_the.jsonl", [
        {"id": k, "ten": d["ten"], "loai": d["loai"], "mo_ta": d.get("mo_ta_tong", ""), "tan_suat": d["tan_suat"],
         "bac": d["bac"], "ma_ngan": d["ma_ngan"], "vids": d["vids"], "don_vi": d["don_vi"]}
        for k, d in sorted(tt.items())])
    ix.ghi_jsonl(thu_muc / "quan_he.jsonl", [
        {"nguon": a, "dich": b, "mo_ta": d.get("mo_ta_tong", ""), "trong_so": round(d["trong_so"], 2),
         "tan_suat": d["tan_suat"], "bac_ket_hop": d["bac_ket_hop"], "ma_ngan": d["ma_ngan"], "vids": d["vids"]}
        for (a, b), d in sorted(qh.items())])
    ix.ghi_jsonl(thu_muc / "cong_dong.jsonl", [
        {"id": c["id"], "cap": c["cap"], "cha": c["cha"], "thanh_vien": c["thanh_vien"],
         "tieu_de": (c.get("bao_cao") or {}).get("tieu_de", ""), "tom_tat": (c.get("bao_cao") or {}).get("tom_tat", ""),
         "muc_do": (c.get("bao_cao") or {}).get("muc_do"),
         "bao_cao": ix.van_ban_bao_cao(c) if c.get("bao_cao") else "", "thuat_toan": thuat_toan} for c in comms])
