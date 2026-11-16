"""Chạy bộ câu hỏi qua các hệ thống và chấm bằng 6 độ đo KHÔNG dùng LLM (graphrag/evaluation/metrics.py).

Cần: Docker đã bật (PostgreSQL + Neo4j đã nạp dữ liệu), OPENROUTER_API_KEY trong .env.

  python scripts/chay_bo_test.py                               # hệ thống đề xuất, data/eval/bo_test_tu_dong.jsonl
  python scripts/chay_bo_test.py --he-thong hybrid_graphrag hybrid_rag ms_graphrag   # so sánh 3 hệ thống
  python scripts/chay_bo_test.py --gioi-han 20                 # chạy thử 20 câu đầu
  python scripts/chay_bo_test.py --loai hieu_luc so_sanh       # chỉ một vài loại câu
  python scripts/chay_bo_test.py --id t001 t077                # vài câu cụ thể
  python scripts/chay_bo_test.py --file data/eval/questions_TV1.jsonl   # bộ câu do nhóm soạn (cùng định dạng)
  python scripts/chay_bo_test.py --tiep                        # chạy tiếp lần trước bị dừng giữa chừng
  python scripts/chay_bo_test.py --he-thong hybrid_graphrag hybrid_rag ms_graphrag --da-duyet --moi-loai 13   # chạy sơ bộ
  python scripts/chay_bo_test.py --cham-lai data/eval/ket_qua/ket_qua_<thời điểm>.jsonl   # chấm lại, không gọi API

Độ đo (k = 5, 10, 40; 40 là ngân sách ngữ cảnh lớn nhất của hệ thống đề xuất: 10 tìm trực tiếp + 30 mở rộng):
  Truy hồi – so danh sách điều khoản hệ thống lấy ra (theo thứ tự) với gold_ids:
    Recall@k        tỉ lệ điều khoản gold nằm trong top-k
    Full Recall@k   1 nếu lấy được TẤT CẢ điều khoản gold trong top-k (quan trọng với câu multi-hop)
    MRR@k           1 / thứ hạng của điều khoản gold đầu tiên
    F2@k            trung bình điều hòa nghiêng về recall của precision@k và recall@k
  Câu trả lời – so khớp dữ kiện kiểm chứng được (mức tiền, số điểm trừ, mã điều khoản trích dẫn):
    Faithfulness      tỉ lệ dữ kiện trong câu trả lời có căn cứ trong ngữ cảnh đã đưa cho LLM (mã trích dẫn phải nằm
                      trong ngữ cảnh). Câu trả lời không nêu dữ kiện nào thì không chấm.
    Answer Relevance  F1 giữa dữ kiện của câu trả lời và của đáp án chuẩn; câu đáp án "chưa/không bị xử phạt" thì
                      1 nếu câu trả lời nói rõ là chưa/không áp dụng.
Ý nghĩa thống kê: paired bootstrap (10.000 lần) cho chênh lệch trung bình giữa hệ thống đề xuất và từng baseline.

Kết quả trong data/eval/ket_qua/: ket_qua_*.jsonl (từng câu), bao_cao_*.md (báo cáo), bao_cao_*.csv (mở bằng Excel).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from graphrag.evaluation.metrics import (answer_relevance_khong_llm, f2_at_k, faithfulness_khong_llm,  # noqa: E402
                                         full_recall_at_k, mrr_at_k, recall_at_k, so_tien_trong)

KS = (5, 10, 40)
TEN_LOAI = {"don": "Đơn", "multi_hop": "Multi-hop", "hieu_luc": "Hiệu lực", "so_sanh": "So sánh"}
TEN_HT = {"hybrid_graphrag": "Hybrid GraphRAG (đề xuất)", "hybrid_rag": "Hybrid RAG (B1)",
          "ms_graphrag": "GraphRAG kiểu Microsoft (B2)"}
NHAN_HT = {"hybrid_graphrag": "Đề xuất", "hybrid_rag": "B1", "ms_graphrag": "B2"}
# Cột hiển thị: (khóa, tên)
COT = ([(f"recall@{k}", f"Recall@{k}") for k in KS] + [(f"full_recall@{k}", f"Full Recall@{k}") for k in KS]
       + [(f"mrr@{k}", f"MRR@{k}") for k in (10,)] + [(f"f2@{k}", f"F2@{k}") for k in KS]
       + [("faithfulness", "Faithfulness"), ("answer_relevance", "Answer Relevance")])
COT_GON = ["recall@10", "full_recall@10", "full_recall@40", "mrr@10", "f2@10", "faithfulness", "answer_relevance"]

__all__ = ["cham", "so_tien_trong", "bootstrap"]


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def ht_cua(r: dict) -> str:
    return r.get("he_thong") or "hybrid_graphrag"


# ---------------------------------------------------------------- chấm một câu

def cham(q: dict, r: dict) -> dict:
    """q: câu hỏi (gold_ids, so_tien, diem_tru, dap_an). r: kết quả đã lưu (truy_hoi, tra_loi, ngu_canh_text,
    trich_dan, trich_dan_la). Trả về các độ đo của câu."""
    gold = q.get("gold_ids") or []
    ds = r.get("truy_hoi") or r.get("ngu_canh") or []
    out = {}
    for k in KS:
        out[f"recall@{k}"] = recall_at_k(gold, ds, k)
        out[f"full_recall@{k}"] = full_recall_at_k(gold, ds, k)
        out[f"mrr@{k}"] = mrr_at_k(gold, ds, k)
        out[f"f2@{k}"] = f2_at_k(gold, ds, k)
    out["faithfulness"] = faithfulness_khong_llm(r.get("tra_loi") or "", r.get("ngu_canh_text") or [],
                                                 r.get("trich_dan") or [], r.get("trich_dan_la") or [])
    out["answer_relevance"] = answer_relevance_khong_llm(r.get("tra_loi") or "", q.get("so_tien") or [],
                                                         q.get("dap_an") or "", q.get("diem_tru"))
    out["gold_thieu"] = [g for g in gold if g not in set(ds)]
    return out


# ---------------------------------------------------------------- tổng hợp, thống kê

def tb(rows: list[dict], key: str) -> float | None:
    v = [r["cham"][key] for r in rows if r["cham"].get(key) is not None]
    return sum(v) / len(v) if v else None


def fmt(x: float | None) -> str:
    return "–" if x is None else f"{x:.3f}"


def bootstrap(a: list[float], b: list[float], lan: int = 10000, seed: int = 42) -> tuple[float, float]:
    """Paired bootstrap: (chênh lệch trung bình a − b, p-value hai phía)."""
    n = len(a)
    if n == 0:
        return 0.0, 1.0
    d = [x - y for x, y in zip(a, b)]
    goc = sum(d) / n
    if all(x == 0 for x in d):
        return 0.0, 1.0
    import numpy as np

    rng = np.random.default_rng(seed)
    m = np.asarray(d)[rng.integers(0, n, size=(lan, n))].mean(axis=1)
    lech = int((m <= 0).sum()) if goc >= 0 else int((m >= 0).sum())
    return goc, min(1.0, 2 * lech / lan)


def bang_theo_loai(rows: list[dict]) -> list[str]:
    ok = [r for r in rows if not r.get("loi")]
    md = ["| Loại | Số câu | " + " | ".join(t for _, t in COT) + " |", "|---|---|" + "---|" * len(COT)]
    for k, ten in list(TEN_LOAI.items()) + [("*", "**Tổng**")]:
        rs = ok if k == "*" else [r for r in ok if r["loai"] == k]
        if rs:
            md.append(f"| {ten} | {len(rs)} | " + " | ".join(fmt(tb(rs, c)) for c, _ in COT) + " |")
    return md


def bao_cao(rows: list[dict], nguon: str, stamp: str, out_dir: Path) -> tuple[Path, Path]:
    he = [h for h in TEN_HT if any(ht_cua(r) == h for r in rows)]
    ok = [r for r in rows if not r.get("loi")]
    md = [f"# Kết quả chạy bộ test — {time.strftime('%d/%m/%Y %H:%M')}", "",
          f"Bộ câu hỏi: `{nguon}` · 6 độ đo không dùng LLM (cách tính: đầu file `scripts/chay_bo_test.py`).", ""]
    if len(he) > 1:
        ten = dict(COT)
        md += ["## So sánh các hệ thống (toàn bộ câu)", "",
               "| Hệ thống | Số câu | " + " | ".join(ten[c] for c in COT_GON) + " |", "|---|---|" + "---|" * len(COT_GON)]
        for h in he:
            rs = [r for r in ok if ht_cua(r) == h]
            md.append(f"| {TEN_HT[h]} | {len(rs)} | " + " | ".join(fmt(tb(rs, c)) for c in COT_GON) + " |")
        if "hybrid_graphrag" in he:
            md += ["", "Chênh lệch so với hệ thống đề xuất (đề xuất − baseline; paired bootstrap, chỉ các câu cả hai "
                   "đều chạy được; * là p < 0,05):", "",
                   "| Độ đo | " + " | ".join(TEN_HT[h] for h in he if h != "hybrid_graphrag") + " |",
                   "|---|" + "---|" * (len(he) - 1)]
            de_xuat = {r["id"]: r["cham"] for r in ok if ht_cua(r) == "hybrid_graphrag"}
            for c in COT_GON:
                cells = []
                for h in he:
                    if h == "hybrid_graphrag":
                        continue
                    kia = {r["id"]: r["cham"] for r in ok if ht_cua(r) == h}
                    chung = [i for i in sorted(set(de_xuat) & set(kia))
                             if de_xuat[i].get(c) is not None and kia[i].get(c) is not None]
                    d, p = bootstrap([de_xuat[i][c] for i in chung], [kia[i][c] for i in chung])
                    cells.append(f"{d:+.3f} (p={p:.3f}){'*' if p < 0.05 else ''}")
                md.append(f"| {ten[c]} | " + " | ".join(cells) + " |")
        md.append("")
    for h in he:
        rs = [r for r in rows if ht_cua(r) == h]
        loi = [r for r in rs if r.get("loi")]
        md += [f"## {TEN_HT[h]}", "", f"{len(rs)} câu · {len(loi)} câu lỗi khi chạy", ""] + bang_theo_loai(rs) + [""]
        xem = [r for r in rs if not r.get("loi") and (r["cham"]["answer_relevance"] < 1
                                                      or (r["cham"]["faithfulness"] or 1) < 1)]
        md += [f"### Câu cần xem lại ({len(xem)}): Answer Relevance hoặc Faithfulness dưới 1", ""]
        for r in xem:
            c = r["cham"]
            ly_do = [f"Answer Relevance {c['answer_relevance']:.2f}"]
            if c["faithfulness"] is not None and c["faithfulness"] < 1:
                ly_do.append(f"Faithfulness {c['faithfulness']:.2f}")
            if c["gold_thieu"]:
                ly_do.append("không lấy được " + ", ".join(c["gold_thieu"]))
            md += [f"#### {r['id']} · {TEN_LOAI.get(r['loai'], r['loai'])} · ngày {r['ngay_ap_dung']}", "",
                   f"**Hỏi:** {r['cau_hoi']}", "", f"**Đáp án chuẩn:** {r['dap_an']} _(căn cứ: {r['can_cu']})_", "",
                   "**Hệ thống trả lời:**", "", "> " + (r.get("tra_loi") or "").replace("\n", "\n> "), "",
                   f"{'; '.join(ly_do)} · Trích dẫn: {', '.join(r.get('trich_dan') or []) or '(không có)'}", ""]
        if loi:
            md += [f"### Câu lỗi khi chạy ({len(loi)})", ""] + [f"- {r['id']}: {r['loi']}" for r in loi] + [""]

    p_md = out_dir / f"bao_cao_{stamp}.md"
    p_md.write_text("\n".join(md), encoding="utf-8")
    p_csv = out_dir / f"bao_cao_{stamp}.csv"
    with open(p_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["he_thong", "id", "loai", "ngay_ap_dung", "cau_hoi", "dap_an", "tra_loi"] + [c for c, _ in COT]
                   + ["gold_ids", "truy_hoi", "trich_dan", "thoi_gian_s", "loi"])
        for r in rows:
            c = r.get("cham") or {}
            w.writerow([ht_cua(r), r["id"], r["loai"], r["ngay_ap_dung"], r["cau_hoi"], r["dap_an"], r.get("tra_loi", "")]
                       + [None if c.get(k) is None else round(c[k], 4) for k, _ in COT]
                       + [" ".join(r["gold_ids"]), " ".join(r.get("truy_hoi") or []), " ".join(r.get("trich_dan") or []),
                          r.get("thoi_gian_s", ""), r.get("loi", "")])
    return p_md, p_csv


def tom_tat_man_hinh(rows: list[dict]) -> None:
    ten = dict(COT)
    print("\n" + f"{'Hệ thống':<10}{'Số câu':>7}" + "".join(f"{ten[c]:>18}" for c in COT_GON))
    for h in TEN_HT:
        rs = [r for r in rows if ht_cua(r) == h and not r.get("loi")]
        if rs:
            print(f"{NHAN_HT[h]:<10}{len(rs):>7}" + "".join(f"{fmt(tb(rs, c)):>18}" for c in COT_GON))
    n_loi = sum(1 for r in rows if r.get("loi"))
    if n_loi:
        print(f"{n_loi} lượt lỗi khi chạy (xem báo cáo).")


# ---------------------------------------------------------------- chạy

def doc_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8-sig") if line.strip()]


def ghi_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in sorted(rows, key=lambda r: (r["id"], ht_cua(r)))), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default="data/eval/bo_test_tu_dong.jsonl")
    ap.add_argument("--he-thong", nargs="+", default=["hybrid_graphrag"], choices=list(TEN_HT),
                    help="hệ thống cần chạy; nhiều hệ thống thì báo cáo có bảng so sánh và kiểm định")
    ap.add_argument("--loai", nargs="*", choices=list(TEN_LOAI))
    ap.add_argument("--id", nargs="*")
    ap.add_argument("--gioi-han", type=int, help="chỉ chạy N câu đầu (sau khi lọc)")
    ap.add_argument("--da-duyet", action="store_true", help="chỉ chạy câu đã rà soát xong (trang_thai = dat hoặc da_sua)")
    ap.add_argument("--moi-loai", type=int, metavar="N", help="lấy tối đa N câu mỗi loại (chạy sơ bộ cân bằng)")
    ap.add_argument("--song-song", type=int, default=3, help="số lượt chạy cùng lúc (mặc định 3)")
    ap.add_argument("--ra", default="data/eval/ket_qua", help="thư mục ghi kết quả")
    ap.add_argument("--tiep", action="store_true", help="chạy tiếp file kết quả gần nhất, bỏ qua lượt đã có")
    ap.add_argument("--cham-lai", metavar="KET_QUA_JSONL", help="chấm lại một file kết quả, không gọi API")
    args = ap.parse_args()

    out_dir = ROOT / args.ra
    out_dir.mkdir(parents=True, exist_ok=True)
    qs = doc_jsonl(ROOT / args.file)
    by_id = {q["id"]: q for q in qs}

    if args.cham_lai:
        p = Path(args.cham_lai)
        rows = doc_jsonl(p)
        for r in rows:
            if not r.get("loi") and r["id"] in by_id:
                q = by_id[r["id"]]
                r.update({k: q[k] for k in ("so_tien", "diem_tru", "gold_ids", "dap_an", "can_cu") if k in q})
                r["cham"] = cham(q, r)
        ghi_jsonl(p, rows)
        p_md, p_csv = bao_cao(rows, args.file, p.stem.replace("ket_qua_", ""), out_dir)
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
    if args.da_duyet:
        qs = [q for q in qs if q.get("trang_thai") in ("dat", "da_sua")]
        print(f"Câu đã rà soát xong: {len(qs)}")
    if args.moi_loai:
        dem: dict[str, int] = {}
        chon = []
        for q in qs:
            if dem.get(q["loai"], 0) < args.moi_loai:
                dem[q["loai"]] = dem.get(q["loai"], 0) + 1
                chon.append(q)
        qs = chon
        print("Số câu theo loại: " + ", ".join(f"{k} {v}" for k, v in dem.items()))
    if args.gioi_han:
        qs = qs[:args.gioi_han]

    rows: list[dict] = []
    if args.tiep:
        cu = sorted(out_dir.glob("ket_qua_*.jsonl"))
        if not cu:
            sys.exit("Chưa có file kết quả nào để chạy tiếp.")
        p_out = cu[-1]
        rows = [r for r in doc_jsonl(p_out) if not r.get("loi")]
        ghi_jsonl(p_out, rows)
        xong = {(r["id"], ht_cua(r)) for r in rows}
        stamp = p_out.stem.replace("ket_qua_", "")
        print(f"Chạy tiếp {p_out.name}: đã có {len(xong)} lượt.")
    else:
        xong = set()
        stamp = time.strftime("%Y%m%d_%H%M")
        p_out = out_dir / f"ket_qua_{stamp}.jsonl"
        p_out.write_text("", encoding="utf-8")
    viec = [(q, h) for h in args.he_thong for q in qs if (q["id"], h) not in xong]

    from graphrag.common.config import load_config
    from graphrag.pipeline import he_thong as ht
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
    n, t_all = len(viec), time.perf_counter()
    print(f"Chạy {n} lượt ({len(args.he_thong)} hệ thống), {args.song_song} lượt cùng lúc. Kết quả ghi dần vào "
          f"{rel(p_out)} (Ctrl+C để dừng, chạy lại với --tiep để tiếp tục).\n")

    def mot_luot(v: tuple[dict, str]) -> dict:
        q, h = v
        r = {k: q.get(k) for k in ("id", "loai", "ngay_ap_dung", "cau_hoi", "dap_an", "so_tien", "diem_tru",
                                   "gold_ids", "can_cu", "cap_voi")}
        r["he_thong"] = h
        t0 = time.perf_counter()
        for lan in range(2):
            try:
                out = ht.answer(res, q["cau_hoi"], he_thong=h, ngay=date.fromisoformat(q["ngay_ap_dung"]))
                break
            except Exception as e:  # noqa: BLE001
                if lan == 1:
                    r["loi"] = f"{type(e).__name__}: {e}"[:300]
                    r["thoi_gian_s"] = round(time.perf_counter() - t0, 1)
                    return r
                time.sleep(5)
        units = out.get("units", [])
        r.update({"tra_loi": out.get("answer", ""), "trich_dan": out.get("citations", []),
                  "trich_dan_la": out.get("unknown_citations", []),
                  "truy_hoi": out.get("retrieved_ids") or [u["id"] for u in units],
                  "ngu_canh": [u["id"] for u in units],
                  "ngu_canh_text": [f"{u.get('ngu_canh') or ''}\n{u.get('noi_dung') or ''}".strip() for u in units],
                  "thoi_gian_s": round(time.perf_counter() - t0, 1)})
        r["cham"] = cham(q, r)
        return r

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.song_song)) as ex:
            futs = [ex.submit(mot_luot, v) for v in viec]
            for i, f in enumerate(as_completed(futs), 1):
                r = f.result()
                with lock:
                    rows.append(r)
                    with open(p_out, "a", encoding="utf-8") as fo:
                        fo.write(json.dumps(r, ensure_ascii=False) + "\n")
                if r.get("loi"):
                    tt = "LỖI " + r["loi"][:70]
                else:
                    c = r["cham"]
                    tt = (f"R@10 {c['recall@10']:.2f}  FR@40 {c['full_recall@40']:.0f}  "
                          f"Faith {fmt(c['faithfulness'])}  AR {c['answer_relevance']:.2f}")
                print(f"[{i:>3}/{n}] {r['id']:<6}{NHAN_HT[r['he_thong']]:<8}{TEN_LOAI.get(r['loai'], r['loai']):<10}"
                      f"{tt}  {r['thoi_gian_s']}s")
    except KeyboardInterrupt:
        print("\nĐã dừng. Chạy lại với --tiep để tiếp tục các lượt còn lại.")
    finally:
        res.close()

    p_md, p_csv = bao_cao(rows, args.file, stamp, out_dir)
    tom_tat_man_hinh(rows)
    print(f"\nTổng thời gian {time.perf_counter() - t_all:.0f}s.")
    print(f"Báo cáo: {rel(p_md)}\nBảng Excel: {rel(p_csv)}\nChi tiết: {rel(p_out)}")


if __name__ == "__main__":
    main()
