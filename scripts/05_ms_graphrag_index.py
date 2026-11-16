"""Bước 5 (baseline B2): dựng chỉ mục GraphRAG kiểu Microsoft rồi nạp vào PostgreSQL (+ Neo4j để xem).

Cần: đã chạy 02 (versions.jsonl), Docker bật (khi nạp), OPENROUTER_API_KEY trong .env.
  python scripts/05_ms_graphrag_index.py --uoc-tinh               # đếm số lượt gọi LLM, không gọi API
  python scripts/05_ms_graphrag_index.py --gioi-han 100           # thử trên 100 đơn vị lấy rải đều để xem chất lượng
  python scripts/05_ms_graphrag_index.py                          # toàn bộ (~3.000 đơn vị)
  python scripts/05_ms_graphrag_index.py --chi-nap --env cloud    # nạp kết quả đã có lên Supabase + AuraDB, không gọi LLM

Mọi lượt gọi LLM được lưu đệm trong data/processed/ms_graphrag/ (cache_*.jsonl): bị dừng giữa chừng thì chạy lại
lệnh cũ để làm tiếp; chạy lại sau khi xong không tốn thêm tiền. Muốn làm lại từ đầu thì xóa thư mục đó.
Kết quả: thuc_the.jsonl, quan_he.jsonl, cong_dong.jsonl, *_emb.npy, thong_ke.md (xem nhanh chất lượng).
Lưu ý: scripts/04_load.py xóa toàn bộ Neo4j trước khi nạp; sau đó chạy lại lệnh này với --chi-nap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from graphrag.common.config import load_config  # noqa: E402
from graphrag.ms_graphrag import indexing as ix  # noqa: E402

THU_MUC = ROOT / "data/processed/ms_graphrag"


def tien_do(ten: str):
    t0 = time.time()

    def f(i: int, n: int) -> None:
        if i == n or i % 10 == 0:
            print(f"\r  {ten}: {i}/{n} ({time.time() - t0:.0f} giây)", end="" if i < n else "\n", flush=True)
    return f


def embed_co_dem(embedder, items: list[tuple[str, str]], ten: str) -> dict[str, list[float]]:
    """Embedding có lưu đệm theo nội dung (đổi mô tả thì tính lại đúng mục đó)."""
    import numpy as np

    p_vec, p_meta = THU_MUC / f"{ten}_emb.npy", THU_MUC / f"{ten}_emb.json"
    cu: dict[str, tuple[str, int]] = {}
    vecs = None
    if p_vec.exists() and p_meta.exists():
        vecs = np.load(p_vec)
        cu = {m["id"]: (m["h"], i) for i, m in enumerate(json.load(open(p_meta, encoding="utf-8")))}
    h = {i: hashlib.sha1(t.encode("utf-8")).hexdigest()[:16] for i, t in items}
    can = [(i, t) for i, t in items if i not in cu or cu[i][0] != h[i]]
    moi = {}
    for k in range(0, len(can), 64):
        lo = can[k:k + 64]
        for (i, _), v in zip(lo, embedder.encode_documents([t[:2000] for _, t in lo])):
            moi[i] = v
        print(f"\r  embedding {ten}: {min(k + 64, len(can))}/{len(can)}", end="", flush=True)
    if can:
        print()
    out = {i: (moi[i] if i in moi else vecs[cu[i][1]]) for i, _ in items}
    ids = [i for i, _ in items]
    np.save(p_vec, np.asarray([out[i] for i in ids], dtype=np.float32))
    json.dump([{"id": i, "h": h[i]} for i in ids], open(p_meta, "w", encoding="utf-8"))
    return {i: list(map(float, out[i])) for i in ids}


def thong_ke(tt: dict, qh: dict, comms: list[dict], thuat_toan: str, so_dv: int, loi: list[str]) -> str:
    loai = Counter(d["loai"] for d in tt.values())
    top = sorted(tt.values(), key=lambda d: -d["tan_suat"])[:25]
    cap = Counter(c["cap"] for c in comms)
    md = ["# Thống kê chỉ mục GraphRAG (kiểu Microsoft)", "",
          f"- Đơn vị văn bản đã trích: {so_dv}",
          f"- Thực thể: {len(tt)} · quan hệ: {len(qh)}",
          f"- Cộng đồng ({thuat_toan}): " + ", ".join(f"cấp {k}: {v}" for k, v in sorted(cap.items())),
          f"- Lỗi (sẽ thử lại khi chạy lại lệnh): {len(loi)}", "",
          "## Thực thể theo loại", ""] + [f"- {k}: {v}" for k, v in loai.most_common()] + [
          "", "## 25 thực thể xuất hiện nhiều nhất", ""] + [
          f"- {d['ten']} ({d['loai']}, {d['tan_suat']} đơn vị): {d.get('mo_ta_tong', '')[:200]}" for d in top] + [
          "", "## 10 cộng đồng cấp 0 lớn nhất", ""]
    for c in sorted([c for c in comms if c["cap"] == 0], key=lambda c: -len(c["thanh_vien"]))[:10]:
        b = c.get("bao_cao") or {}
        md += [f"### {c['id']} · {len(c['thanh_vien'])} thực thể · {b.get('tieu_de', '(chưa có báo cáo)')}", "",
               b.get("tom_tat", ""), ""]
    if loi:
        md += ["## Lỗi", ""] + [f"- {x}" for x in loi[:50]]
    return "\n".join(md)


def nap(cfg: dict, khong_neo4j: bool) -> None:
    import numpy as np

    from graphrag.storage import ms_store, postgres

    tt = ix.doc_jsonl(THU_MUC / "thuc_the.jsonl")
    qh = ix.doc_jsonl(THU_MUC / "quan_he.jsonl")
    cd = ix.doc_jsonl(THU_MUC / "cong_dong.jsonl")
    if not tt:
        sys.exit("Chưa có data/processed/ms_graphrag/thuc_the.jsonl → chạy lệnh không có --chi-nap trước.")

    def emb(ten):
        v = np.load(THU_MUC / f"{ten}_emb.npy")
        return {m["id"]: v[i] for i, m in enumerate(json.load(open(THU_MUC / f"{ten}_emb.json", encoding="utf-8")))}

    conn = postgres.connect(cfg)
    ms_store.tao_bang(conn, (ROOT / "db/ms_graphrag.sql").read_text(encoding="utf-8"))
    d = ms_store.nap(conn, tt, qh, cd, emb("thuc_the"), emb("cong_dong"))
    conn.close()
    print("[PostgreSQL] " + ", ".join(f"{k} {v}" for k, v in d.items()))
    if not khong_neo4j:
        from graphrag.storage import neo4j_store

        try:
            drv = neo4j_store.connect(cfg)
            print("[Neo4j] " + ", ".join(f"{k} {v}" for k, v in ms_store.nap_neo4j(drv, tt, qh, cd).items()))
            drv.close()
        except Exception as e:  # noqa: BLE001 – Neo4j chỉ để xem, truy vấn dùng PostgreSQL
            print(f"[Neo4j] bỏ qua ({type(e).__name__}: {str(e)[:100]})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", default="local", choices=["local", "cloud"])
    ap.add_argument("--gioi-han", type=int, help="chỉ dùng N đơn vị văn bản đầu (thử chất lượng, ít tốn tiền)")
    ap.add_argument("--van-ban", nargs="*", help="chỉ một số văn bản, vd. ND168_2024 TT38_2024")
    ap.add_argument("--song-song", type=int, default=8, help="số lượt gọi LLM cùng lúc")
    ap.add_argument("--gleaning", type=int, help="số vòng hỏi lại thực thể bị sót (mặc định theo cấu hình)")
    ap.add_argument("--uoc-tinh", action="store_true", help="chỉ đếm số lượt gọi LLM cần thiết")
    ap.add_argument("--chi-nap", action="store_true", help="không gọi LLM, chỉ nạp kết quả đã có vào cơ sở dữ liệu")
    ap.add_argument("--khong-nap", action="store_true", help="dựng chỉ mục nhưng chưa nạp vào cơ sở dữ liệu")
    ap.add_argument("--khong-neo4j", action="store_true", help="không nạp bản sao đồ thị thực thể vào Neo4j")
    args = ap.parse_args()
    cfg = load_config(args.env)
    mc = cfg.get("ms_graphrag", {})
    THU_MUC.mkdir(parents=True, exist_ok=True)

    if args.chi_nap:
        nap(cfg, args.khong_neo4j)
        return

    versions = ix.doc_jsonl(ROOT / cfg["paths"]["processed"] / "versions.jsonl")
    units = ix.don_vi_van_ban(versions, args.van_ban, args.gioi_han)
    gleaning = mc.get("gleaning", 0) if args.gleaning is None else args.gleaning
    c_tx = ix.Cache(THU_MUC / "cache_trich_xuat.jsonl")
    con_lai = sum(u["vid"] not in c_tx for u in units)
    print(f"{len(units)} đơn vị văn bản · đã trích trước đó {len(units) - con_lai} · cần trích {con_lai} "
          f"(mô hình {mc.get('model', cfg['llm']['model'])}, gleaning {gleaning})")
    if args.uoc_tinh:
        print(f"Ước tính: khoảng {con_lai * (1 + gleaning)} lượt trích xuất + vài trăm lượt tóm tắt mô tả và báo cáo "
              f"cộng đồng. Chạy thử --gioi-han 100 rồi xem số dư OpenRouter để biết chi phí thực tế.")
        return

    from graphrag.llm import LLM
    from graphrag.openrouter import get_client

    llm = LLM(get_client(cfg), mc.get("model", cfg["llm"]["model"]), 0.0, mc.get("max_tokens", 3000))
    t0 = time.time()
    print("1/5 Trích thực thể và quan hệ")
    try:
        kq, loi = ix.trich_xuat(llm, units, c_tx, args.song_song, gleaning, tien_do("trích xuất"))
    except ix.LoiKhongTheTiepTuc as e:
        print(f"\nDừng: mọi khóa API đều bị từ chối vì tài khoản/hạn mức: {e}")
        sys.exit("Nâng hạn mức khóa ở https://openrouter.ai/settings/keys hoặc nạp credits OpenRouter, hoặc thêm/nạp "
                 "OPENAI_API_KEY (dự phòng), rồi chạy lại đúng lệnh này (phần đã trích được giữ lại, không tính tiền lại).")
    if not kq:
        sys.exit("Chưa trích được đơn vị nào, dừng trước các bước sau. Xem lỗi ở trên rồi chạy lại.")
    if loi:
        print(f"  {len(loi)} đơn vị lỗi, ví dụ: {loi[0]}")

    print("2/5 Gộp và tóm tắt mô tả")
    tt, qh = ix.gop(kq, {u["vid"]: u["id"] for u in units})
    loi += ix.tom_tat_mo_ta(llm, tt, qh, ix.Cache(THU_MUC / "cache_tom_tat.jsonl"), args.song_song,
                            mc.get("nguong_tom_tat", 200), tien_do=tien_do("tóm tắt"))
    print(f"  {len(tt)} thực thể, {len(qh)} quan hệ")

    print("3/5 Phân cộng đồng (Leiden phân cấp)")
    comms, thuat_toan = ix.cong_dong(tt, qh, mc.get("max_cluster_size", 10), mc.get("max_level", 3))
    if thuat_toan != "leiden":
        print("  Chưa cài leidenalg → dùng Louvain của networkx (pip install -e \".[msgraph]\" để dùng Leiden)")
    print(f"  {len(comms)} cộng đồng: " + ", ".join(f"cấp {k} {v}" for k, v in sorted(Counter(c['cap'] for c in comms).items())))

    print("4/5 Báo cáo cộng đồng")
    loi += ix.bao_cao_cong_dong(llm, comms, tt, qh, ix.Cache(THU_MUC / "cache_bao_cao.jsonl"), args.song_song,
                                tien_do=tien_do("báo cáo"))
    ix.luu_ket_qua(THU_MUC, tt, qh, comms, thuat_toan)
    dem = getattr(llm.client, "dem", {})
    if dem:
        print("  Lượt gọi LLM lần chạy này theo khóa: " + ", ".join(f"{k} {v}" for k, v in dem.items()))

    print("5/5 Embedding")
    from graphrag.embedding import get_embedder

    emb = get_embedder(cfg)
    embed_co_dem(emb, [(k, f"{d['ten']}: {d.get('mo_ta_tong', '')}") for k, d in sorted(tt.items())], "thuc_the")
    embed_co_dem(emb, [(c["id"], f"{(c.get('bao_cao') or {}).get('tieu_de', '')}. {(c.get('bao_cao') or {}).get('tom_tat', '')}")
                       for c in comms], "cong_dong")
    (THU_MUC / "thong_ke.md").write_text(thong_ke(tt, qh, comms, thuat_toan, len(kq), loi), encoding="utf-8")
    print(f"Xong phần dựng chỉ mục sau {time.time() - t0:.0f} giây. Xem nhanh chất lượng: data/processed/ms_graphrag/thong_ke.md")
    if loi:
        print(f"{len(loi)} lượt gọi lỗi: chạy lại đúng lệnh này để thử lại các phần còn thiếu.")
    if not args.khong_nap:
        nap(cfg, args.khong_neo4j)


if __name__ == "__main__":
    main()
