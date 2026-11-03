"""Chạy một bộ câu hỏi qua pipeline GraphRAG thật và chấm tự động.

Cần: Docker đã bật (PostgreSQL + Neo4j đã nạp dữ liệu), OPENROUTER_API_KEY trong .env.

  python scripts/chay_bo_test.py                               # 200 câu trong data/eval/bo_test_tu_dong.jsonl
  python scripts/chay_bo_test.py --gioi-han 20                 # chạy thử 20 câu đầu
  python scripts/chay_bo_test.py --loai hieu_luc so_sanh       # chỉ một vài loại
  python scripts/chay_bo_test.py --id t001 t077                # vài câu cụ thể
  python scripts/chay_bo_test.py --file data/eval/questions_TV1.jsonl   # bộ câu do nhóm soạn (cùng định dạng)
  python scripts/chay_bo_test.py --tiep                        # chạy tiếp lần trước bị dừng giữa chừng
  python scripts/chay_bo_test.py --cham-lai data/eval/ket_qua/ket_qua_20261102_2130.jsonl   # chỉ chấm lại, không gọi API
  python scripts/chay_bo_test.py --ragas                       # chấm thêm 4 độ đo RAGAS (cần pip install -e ".[ragas]")
  python scripts/chay_bo_test.py --cham-lai <file kết quả> --ragas   # chấm RAGAS cho lần chạy đã có (không chạy lại GraphRAG)

Kết quả trong data/eval/ket_qua/:
  ket_qua_<thời điểm>.jsonl   từng câu: câu trả lời, trích dẫn, ngữ cảnh, điểm chấm
  bao_cao_<thời điểm>.md      báo cáo tổng hợp theo loại câu + danh sách câu sai để đọc lại
  bao_cao_<thời điểm>.csv     bảng từng câu, mở bằng Excel

Cách chấm (tự động, nên chỉ là ước lượng):
  - Tiền đúng   : mọi số tiền trong so_tien đều xuất hiện trong câu trả lời (hiểu cả "18.000.000" và "18 triệu").
                  Câu có so_tien rỗng (vd. "chưa bị xử phạt"): đúng nếu không nêu mức tiền nào trong
                  so_tien_khong_duoc_co (mức của phiên bản khác ngày).
  - Điểm đúng   : câu có diem_tru thì câu trả lời phải nêu "N điểm".
  - Đúng        : tiền đúng và (nếu có) điểm đúng.
  - Ngữ cảnh đủ : mọi mã gold đều nằm trong ngữ cảnh đưa cho LLM (đo phần truy hồi + đồ thị).
  - Trích dẫn   : recall = tỉ lệ gold được trích; precision = tỉ lệ trích dẫn trúng gold
                  (tính cả khi trích khoản cha/điểm con của gold).
  - RAGAS (--ragas): Faithfulness, Answer Relevance, Context Precision, Context Recall do LLM giám khảo chấm
                  (evaluation.judge_model, mặc định openai/gpt-4o; đổi bằng --ragas-model), cộng Context
                  Precision/Recall (ID) tính theo mã gold, không dùng LLM. Xem graphrag/evaluation/ragas_eval.py.
Chi phí: mỗi câu 1–2 lượt gpt-4o-mini + 1 embedding + 1 rerank; --ragas thêm khoảng 6–10 lượt gọi mô hình giám khảo
mỗi câu (đắt hơn nhiều). Chạy thử --gioi-han 20 rồi xem số dư trên openrouter.ai để ước lượng trước khi chạy cả bộ.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


RAGAS_COT = ["faithfulness", "answer_relevancy", "llm_context_precision_with_reference", "context_recall",
             "id_based_context_precision", "id_based_context_recall"]
TEN_LOAI = {"don": "Đơn", "multi_hop": "Multi-hop", "hieu_luc": "Hiệu lực", "so_sanh": "So sánh"}


# ---------------------------------------------------------------- chấm điểm

def so_tien_trong(text: str) -> set[int]:
    """Mọi mức tiền nêu trong câu trả lời: '18.000.000', '18 triệu', 'từ 18 đến 20 triệu', '500 nghìn'."""
    t = text.replace("\u00a0", " ")
    out = {int(x.replace(".", "").replace(",", "")) for x in re.findall(r"\d{1,3}(?:[.,]\d{3})+(?![.,]?\d)", t)}

    def num(s: str) -> float:
        return float(s.replace(",", "."))

    for a, b, dv in re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:đến|–|-|tới)\s*(\d+(?:[.,]\d+)?)\s*(triệu|nghìn|ngàn)", t):
        k = 1_000_000 if dv == "triệu" else 1_000
        out |= {round(num(a) * k), round(num(b) * k)}
    for a, dv in re.findall(r"(\d+(?:[.,]\d+)?)\s*(triệu|nghìn|ngàn)", t):
        out.add(round(num(a) * (1_000_000 if dv == "triệu" else 1_000)))
    return out


def _lien_quan(cite: str, gold: list[str]) -> bool:
    return any(cite == g or g.startswith(cite + ".") or cite.startswith(g + ".") for g in gold)


def cham(q: dict, out: dict) -> dict:
    ans = out.get("answer") or ""
    gold = q.get("gold_ids") or []
    ctx = {u["id"] for u in out.get("units", [])}
    cited = out.get("citations") or []
    tien = so_tien_trong(ans)
    if q.get("so_tien"):
        thieu_tien = [x for x in q["so_tien"] if x not in tien]
        tien_dung = not thieu_tien
    else:
        cam = q.get("so_tien_khong_duoc_co") or []
        thieu_tien = [x for x in cam if x in tien]          # ở đây: mức tiền KHÔNG được nêu mà vẫn nêu
        tien_dung = not thieu_tien
    diem_dung = None
    if q.get("diem_tru"):
        n = q["diem_tru"]
        diem_dung = bool(re.search(rf"(?<!\d)0?{n}\s*điểm", ans))
    ctx_hit = [g for g in gold if g in ctx]
    cite_hit = [g for g in gold if g in cited]
    cite_ok = [c for c in cited if _lien_quan(c, gold + (q.get("nguon_sua_doi") or []))]
    return {
        "dung": tien_dung and diem_dung is not False,
        "tien_dung": tien_dung, "diem_dung": diem_dung,
        "tien_lech": thieu_tien,
        "ngu_canh_du": len(ctx_hit) == len(gold), "ngu_canh_recall": len(ctx_hit) / len(gold) if gold else 1.0,
        "gold_thieu_ngu_canh": [g for g in gold if g not in ctx],
        "trich_dan_recall": len(cite_hit) / len(gold) if gold else 1.0,
        "trich_dan_precision": len(cite_ok) / len(cited) if cited else 0.0,
        "so_trich_dan": len(cited),
    }


# ---------------------------------------------------------------- báo cáo

def pct(xs: list[bool]) -> str:
    return f"{100 * sum(xs) / len(xs):.0f}%" if xs else "–"


def tb(xs: list[float]) -> str:
    return f"{sum(xs) / len(xs):.2f}" if xs else "–"


def bao_cao(rows: list[dict], nguon: str, stamp: str, out_dir: Path) -> tuple[Path, Path]:
    ok = [r for r in rows if not r.get("loi")]
    loi = [r for r in rows if r.get("loi")]
    nhom = defaultdict(list)
    for r in ok:
        nhom[r["loai"]].append(r)

    def dong(ten: str, rs: list[dict]) -> str:
        c = [r["cham"] for r in rs]
        diem = [x["diem_dung"] for x in c if x["diem_dung"] is not None]
        return (f"| {ten} | {len(rs)} | **{pct([x['dung'] for x in c])}** | {pct([x['tien_dung'] for x in c])} | "
                f"{pct(diem)} | {pct([x['ngu_canh_du'] for x in c])} | {tb([x['ngu_canh_recall'] for x in c])} | "
                f"{tb([x['trich_dan_recall'] for x in c])} | {tb([x['trich_dan_precision'] for x in c])} | "
                f"{tb([r['thoi_gian_s'] for r in rs])} |")

    md = [f"# Kết quả chạy bộ test — {time.strftime('%d/%m/%Y %H:%M')}", "",
          f"Bộ câu hỏi: `{nguon}` · {len(rows)} câu · {len(loi)} câu lỗi khi chạy", "",
          "| Loại | Số câu | Đúng | Tiền đúng | Điểm trừ đúng | Ngữ cảnh đủ gold | Recall ngữ cảnh | "
          "Recall trích dẫn | Precision trích dẫn | Thời gian TB (s) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for k in TEN_LOAI:
        if nhom.get(k):
            md.append(dong(TEN_LOAI[k], nhom[k]))
    md.append(dong("**Tổng**", ok))
    # cặp hiệu lực: cả hai ngày đều đúng
    by_id = {r["id"]: r for r in ok}
    cap = {tuple(sorted((r["id"], r["cap_voi"]))) for r in ok if r.get("cap_voi") in by_id}
    if cap:
        dung_ca_cap = sum(by_id[a]["cham"]["dung"] and by_id[b]["cham"]["dung"] for a, b in cap)
        md += ["", f"Cặp câu hiệu lực (cùng câu hỏi, khác ngày) đúng cả hai: **{dung_ca_cap}/{len(cap)}**."]
    co_ragas = [r for r in ok if r.get("ragas")]
    if co_ragas:
        from graphrag.evaluation.ragas_eval import COT
        cot = [c for c in COT if any(r["ragas"].get(c) is not None for r in co_ragas)]
        nhom_r = defaultdict(list)
        for r in co_ragas:
            nhom_r[r["loai"]].append(r)

        def tb_r(rs: list[dict], c: str) -> str:
            v = [r["ragas"][c] for r in rs if r["ragas"].get(c) is not None]
            return f"{sum(v) / len(v):.2f}" if v else "–"

        md += ["", f"### Độ đo RAGAS ({len(co_ragas)} câu)", "",
               "| Loại | Số câu | " + " | ".join(COT[c] for c in cot) + " |", "|---|---|" + "---|" * len(cot)]
        for k in list(TEN_LOAI) + ["*"]:
            rs = co_ragas if k == "*" else nhom_r.get(k, [])
            if rs:
                ten = "**Tổng**" if k == "*" else TEN_LOAI[k]
                md.append(f"| {ten} | {len(rs)} | " + " | ".join(tb_r(rs, c) for c in cot) + " |")
        md += ["", "Thang 0–1, càng cao càng tốt; ô \"–\" là giám khảo không trả kết quả hợp lệ. Faithfulness chỉ so câu "
               "trả lời với ngữ cảnh (không so với đáp án chuẩn), nên đọc cùng cột *Đúng* ở bảng trên. "
               "Precision (ID) thấp là bình thường vì ngữ cảnh gồm nhiều điều khoản, gold chỉ 1–3 mã."]
    md += ["", "Cách đọc: *Đúng* = nêu đúng mọi mức tiền (và số điểm trừ nếu có). *Ngữ cảnh đủ gold* = mọi điều khoản "
           "căn cứ đều được tìm thấy và đưa cho LLM; nếu cột này thấp thì lỗi ở bước tìm kiếm/đồ thị, nếu cột này cao mà "
           "*Đúng* thấp thì lỗi ở bước sinh câu trả lời. Chấm tự động theo số tiền nên chỉ là ước lượng: "
           "hãy đọc lại các câu sai bên dưới.", ""]

    sai = [r for r in ok if not r["cham"]["dung"]]
    md += [f"## Câu sai ({len(sai)})", ""]
    for r in sai:
        c = r["cham"]
        ly_do = []
        if not c["tien_dung"]:
            ly_do.append(("nêu mức tiền của phiên bản khác: " if not r["so_tien"] else "thiếu mức tiền: ")
                         + ", ".join(f"{x:,}".replace(",", ".") for x in c["tien_lech"]))
        if c["diem_dung"] is False:
            ly_do.append(f"không nêu đúng {r['diem_tru']} điểm trừ")
        if c["gold_thieu_ngu_canh"]:
            ly_do.append("ngữ cảnh thiếu " + ", ".join(c["gold_thieu_ngu_canh"]))
        md += [f"### {r['id']} · {TEN_LOAI.get(r['loai'], r['loai'])} · ngày {r['ngay_ap_dung']}", "",
               f"**Hỏi:** {r['cau_hoi']}", "",
               f"**Đáp án đúng:** {r['dap_an']} _(căn cứ: {r['can_cu']})_", "",
               "**Hệ thống trả lời:**", "", "> " + (r["tra_loi"] or "").replace("\n", "\n> "), "",
               f"Lý do: {'; '.join(ly_do) or '–'} · Trích dẫn: {', '.join(r['trich_dan']) or '(không có)'}", ""]
    if loi:
        md += [f"## Câu lỗi khi chạy ({len(loi)})", ""] + [f"- {r['id']}: {r['loi']}" for r in loi] + [""]

    p_md = out_dir / f"bao_cao_{stamp}.md"
    p_md.write_text("\n".join(md), encoding="utf-8")
    p_csv = out_dir / f"bao_cao_{stamp}.csv"
    with open(p_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "loai", "ngay_ap_dung", "cau_hoi", "dap_an", "tra_loi", "dung", "tien_dung", "diem_dung",
                    "ngu_canh_du", "ngu_canh_recall", "trich_dan_recall", "trich_dan_precision", "gold_ids",
                    "trich_dan", "thoi_gian_s", "loi"] + [f"ragas_{c}" for c in RAGAS_COT])
        for r in rows:
            c = r.get("cham") or {}
            w.writerow([r["id"], r["loai"], r["ngay_ap_dung"], r["cau_hoi"], r["dap_an"], r.get("tra_loi", ""),
                        c.get("dung"), c.get("tien_dung"), c.get("diem_dung"), c.get("ngu_canh_du"),
                        round(c.get("ngu_canh_recall", 0), 2), round(c.get("trich_dan_recall", 0), 2),
                        round(c.get("trich_dan_precision", 0), 2), " ".join(r["gold_ids"]),
                        " ".join(r.get("trich_dan", [])), r.get("thoi_gian_s", ""), r.get("loi", "")]
                       + [(r.get("ragas") or {}).get(c) for c in RAGAS_COT])
    return p_md, p_csv


def tom_tat_man_hinh(rows: list[dict]) -> None:
    ok = [r for r in rows if not r.get("loi")]
    print(f"\n{'Loại':<11}{'Số câu':>7}{'Đúng':>7}{'Tiền':>7}{'Điểm':>7}{'Ng.cảnh':>9}")
    nhom = defaultdict(list)
    for r in ok:
        nhom[r["loai"]].append(r["cham"])
    for k, ten in list(TEN_LOAI.items()) + [("*", "Tổng")]:
        c = [x for v in nhom.values() for x in v] if k == "*" else nhom.get(k, [])
        if not c:
            continue
        diem = [x["diem_dung"] for x in c if x["diem_dung"] is not None]
        print(f"{ten:<11}{len(c):>7}{pct([x['dung'] for x in c]):>7}{pct([x['tien_dung'] for x in c]):>7}"
              f"{pct(diem):>7}{pct([x['ngu_canh_du'] for x in c]):>9}")
    if len(ok) < len(rows):
        print(f"{len(rows) - len(ok)} câu lỗi khi chạy (xem báo cáo).")
    co = [r["ragas"] for r in ok if r.get("ragas")]
    if co:
        ten = {"faithfulness": "Faithfulness", "answer_relevancy": "Answer Relevance",
               "llm_context_precision_with_reference": "Context Precision", "context_recall": "Context Recall",
               "id_based_context_precision": "Context Precision (ID)", "id_based_context_recall": "Context Recall (ID)"}
        print(f"\nRAGAS ({len(co)} câu, trung bình 0–1):")
        for c in RAGAS_COT:
            v = [x[c] for x in co if x.get(c) is not None]
            if v:
                print(f"  {ten[c]:<24}{sum(v) / len(v):.3f}   ({len(v)} câu có điểm)")


# ---------------------------------------------------------------- chạy

def chay_ragas(rows: list[dict], cfg: dict, args, p_out: Path) -> None:
    """Gắn điểm RAGAS vào từng dòng (r["ragas"]) rồi ghi lại file kết quả."""
    try:
        from graphrag.evaluation.ragas_eval import cham_ragas
        import ragas  # noqa: F401
    except ImportError as e:
        print(f"\nChưa cài RAGAS ({e.name}). Chạy: pip install -e \".[ragas]\" rồi chấm lại bằng:\n"
              f"  python scripts/chay_bo_test.py --cham-lai {rel(p_out)} --ragas")
        return
    can = [r for r in rows if not r.get("loi") and (args.ragas_lai or not r.get("ragas"))]
    thieu = [r for r in can if not r.get("ngu_canh_text")]
    if thieu:
        print(f"{len(thieu)} câu không có nội dung ngữ cảnh (kết quả cũ) nên bỏ qua RAGAS; chạy lại các câu đó để chấm.")
        can = [r for r in can if r.get("ngu_canh_text")]
    if not can:
        print("Không có câu nào cần chấm RAGAS.")
        return
    model = args.ragas_model or cfg.get("evaluation", {}).get("judge_model", "openai/gpt-4o")
    print(f"\nChấm RAGAS {len(can)} câu, giám khảo {model}…")
    diem = cham_ragas(can, cfg, model=model, song_song=max(1, args.song_song))
    for r, d in zip(can, diem):
        r["ragas"] = d
    p_out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sorted(rows, key=lambda r: r["id"])),
                     encoding="utf-8")


def doc_cau_hoi(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8-sig") if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default="data/eval/bo_test_tu_dong.jsonl")
    ap.add_argument("--loai", nargs="*", choices=list(TEN_LOAI))
    ap.add_argument("--id", nargs="*")
    ap.add_argument("--gioi-han", type=int, help="chỉ chạy N câu đầu (sau khi lọc)")
    ap.add_argument("--song-song", type=int, default=3, help="số câu chạy cùng lúc (mặc định 3)")
    ap.add_argument("--ra", default="data/eval/ket_qua", help="thư mục ghi kết quả")
    ap.add_argument("--tiep", action="store_true", help="chạy tiếp file kết quả gần nhất, bỏ qua câu đã có")
    ap.add_argument("--cham-lai", metavar="KET_QUA_JSONL", help="chấm lại một file kết quả, không gọi API")
    ap.add_argument("--ragas", action="store_true", help="chấm thêm Faithfulness, Answer Relevance, "
                    "Context Precision, Context Recall bằng RAGAS (gọi LLM giám khảo, tốn thêm chi phí)")
    ap.add_argument("--ragas-model", help="mô hình giám khảo trên OpenRouter (mặc định evaluation.judge_model)")
    ap.add_argument("--ragas-lai", action="store_true", help="chấm RAGAS lại cả những câu đã có điểm RAGAS")
    args = ap.parse_args()

    src = ROOT / args.file
    out_dir = ROOT / args.ra
    out_dir.mkdir(parents=True, exist_ok=True)
    qs = doc_cau_hoi(src)
    by_id = {q["id"]: q for q in qs}

    if args.cham_lai:
        p = Path(args.cham_lai)
        rows = [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]
        for r in rows:
            if not r.get("loi") and r["id"] in by_id:
                q = {**by_id[r["id"]]}
                r.update({k: q[k] for k in ("so_tien", "diem_tru", "gold_ids", "dap_an", "can_cu") if k in q})
                r["cham"] = cham(q, {"answer": r["tra_loi"], "citations": r["trich_dan"],
                                     "units": [{"id": i} for i in r["ngu_canh"]]})
        stamp = p.stem.replace("ket_qua_", "")
        if args.ragas:
            from graphrag.common.config import load_config
            chay_ragas(rows, load_config(), args, p)
        p_md, p_csv = bao_cao(rows, args.file, stamp, out_dir)
        tom_tat_man_hinh(rows)
        print(f"\nBáo cáo: {rel(p_md)}\nBảng Excel: {rel(p_csv)}")
        return

    bo = [q for q in qs if q.get("trang_thai") == "loai"]
    if bo:
        print(f"Bỏ qua {len(bo)} câu đã bị loại khi rà soát (trang_thai = loai).")
        qs = [q for q in qs if q.get("trang_thai") != "loai"]
    if args.loai:
        qs = [q for q in qs if q["loai"] in args.loai]
    if args.id:
        qs = [q for q in qs if q["id"] in set(args.id)]
    if args.gioi_han:
        qs = qs[:args.gioi_han]

    rows: list[dict] = []
    if args.tiep:
        cu = sorted(out_dir.glob("ket_qua_*.jsonl"))
        if not cu:
            sys.exit("Chưa có file kết quả nào để chạy tiếp.")
        p_out = cu[-1]
        rows = [r for r in (json.loads(line) for line in open(p_out, encoding="utf-8") if line.strip())
                if not r.get("loi")]
        xong = {r["id"] for r in rows}
        p_out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        qs = [q for q in qs if q["id"] not in xong]
        stamp = p_out.stem.replace("ket_qua_", "")
        print(f"Chạy tiếp {p_out.name}: đã có {len(xong)} câu, còn {len(qs)} câu.")
    else:
        stamp = time.strftime("%Y%m%d_%H%M")
        p_out = out_dir / f"ket_qua_{stamp}.jsonl"
        p_out.write_text("", encoding="utf-8")

    from graphrag.common.config import load_config
    from graphrag.pipeline import graph_rag
    from graphrag.resources import Resources

    res = Resources(load_config())
    print("Kiểm tra kết nối PostgreSQL, Neo4j…")
    st = res.check()
    if not st["postgres"]["ok"] or not st["neo4j"]["ok"]:
        print(f"  PostgreSQL: {st['postgres']}\n  Neo4j: {st['neo4j']}")
        sys.exit("Chưa kết nối được cơ sở dữ liệu. Mở Docker Desktop rồi chạy:\n"
                 "  docker compose -f db/docker-compose.yml --env-file .env up -d\n"
                 "đợi khoảng 30 giây rồi chạy lại.")
    print("Khởi tạo mô hình và chỉ mục BM25…")
    _ = (res.embedder, res.llm, res.bm25)        # tạo trước, tránh các luồng cùng tạo

    lock = threading.Lock()
    n, t_all = len(qs), time.perf_counter()
    print(f"Chạy {n} câu, {args.song_song} câu cùng lúc. Kết quả ghi dần vào {rel(p_out)} "
          f"(Ctrl+C để dừng, chạy lại với --tiep để tiếp tục).\n")

    def mot_cau(q: dict) -> dict:
        r = {k: q.get(k) for k in ("id", "loai", "ngay_ap_dung", "cau_hoi", "dap_an", "so_tien", "diem_tru",
                                   "gold_ids", "can_cu", "cap_voi")}
        t0 = time.perf_counter()
        for lan in range(2):
            try:
                out = graph_rag.answer(res, q["cau_hoi"], ngay=date.fromisoformat(q["ngay_ap_dung"]))
                break
            except Exception as e:  # noqa: BLE001
                if lan == 1:
                    r["loi"] = f"{type(e).__name__}: {e}"[:300]
                    r["thoi_gian_s"] = round(time.perf_counter() - t0, 1)
                    return r
                time.sleep(5)
        r.update({"tra_loi": out.get("answer", ""), "trich_dan": out.get("citations", []),
                  "ngu_canh": [u["id"] for u in out.get("units", [])],
                  "ngu_canh_text": [f"{u.get('ngu_canh') or ''}\n{u.get('noi_dung') or ''}".strip()
                                    for u in out.get("units", [])],
                  "ngu_canh_tu_do_thi": sum(u.get("origin") == "graph" for u in out.get("units", [])),
                  "thoi_gian_s": round(time.perf_counter() - t0, 1), "cham": cham(q, out)})
        return r

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.song_song)) as ex:
            futs = [ex.submit(mot_cau, q) for q in qs]
            for i, f in enumerate(as_completed(futs), 1):
                r = f.result()
                with lock:
                    rows.append(r)
                    with open(p_out, "a", encoding="utf-8") as fo:
                        fo.write(json.dumps(r, ensure_ascii=False) + "\n")
                if r.get("loi"):
                    trang_thai = "LỖI  " + r["loi"][:70]
                else:
                    c = r["cham"]
                    trang_thai = (f"{'ĐÚNG' if c['dung'] else 'SAI '}  tiền {'✓' if c['tien_dung'] else '✗'}"
                                  + (f"  điểm {'✓' if c['diem_dung'] else '✗'}" if c["diem_dung"] is not None else "")
                                  + f"  ngữ cảnh {sum(g in r['ngu_canh'] for g in r['gold_ids'])}/{len(r['gold_ids'])}")
                print(f"[{i:>3}/{n}] {r['id']:<6}{TEN_LOAI.get(r['loai'], r['loai']):<10}{trang_thai}  {r['thoi_gian_s']}s")
    except KeyboardInterrupt:
        print("\nĐã dừng. Chạy lại với --tiep để tiếp tục các câu còn lại.")
    finally:
        res.close()

    rows.sort(key=lambda r: r["id"])
    if args.ragas:
        chay_ragas(rows, res.cfg, args, p_out)
    p_md, p_csv = bao_cao(rows, args.file, stamp, out_dir)
    tom_tat_man_hinh(rows)
    print(f"\nTổng thời gian {time.perf_counter() - t_all:.0f}s.")
    print(f"Báo cáo: {rel(p_md)}\nBảng Excel: {rel(p_csv)}\nChi tiết: {rel(p_out)}")


if __name__ == "__main__":
    main()
