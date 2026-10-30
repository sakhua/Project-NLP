"""Bước 4: nạp dữ liệu đã xử lý vào PostgreSQL và Neo4j, rồi kiểm tra đồng bộ mã định danh.

Phụ trách: TV1 (viết), TV2 (chạy và kiểm tra).
Chạy trên máy của nhóm:
  python scripts/04_load.py                      # vào DB local (Docker), đọc .env
  python scripts/04_load.py --env cloud          # lên Supabase + AuraDB, đọc .env.cloud
  python scripts/04_load.py --chi postgres       # chỉ nạp PostgreSQL (khi chưa bật Neo4j)
  python scripts/04_load.py --tao-lai-bang       # xóa bảng don_vi cũ (lược đồ trước khi có phiên bản) rồi tạo lại

Mặc định mỗi lần chạy XÓA dữ liệu văn bản cũ rồi nạp lại toàn bộ (dữ liệu nhỏ, chạy dưới 1 phút trên máy),
nên chạy lại bao nhiêu lần cũng được. Nhật ký hỏi đáp (hoi_dap_log) không bị xóa.

Đầu vào (tạo bởi các bước 1–3):
  data/manifest.csv                        -> bảng van_ban, node VanBan
  data/processed/versions.jsonl            -> bảng don_vi (mỗi dòng một phiên bản, đã có hieu_luc_tu/den)
                                              + node Neo4j (một node cho mỗi mã đơn vị) + cạnh THUOC
  data/processed/embedding.npy + embedding_ids.json (vid) -> cột don_vi.embedding
  data/processed/references.jsonl          -> cạnh THAM_CHIEU
  data/processed/amendments.jsonl          -> cạnh SUA_DOI / THAY_THE / BO_SUNG / BAI_BO
Ngày hiệu lực đã được tính ở bước 2 (graphrag/parsing/versioning.py), bước này KHÔNG tính lại.
Thiết kế: docs/thiet_ke_do_thi.md. Hướng dẫn chạy và theo dõi: docs/huong_dan_chay_db.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from graphrag.common.config import load_config  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8")] if path.exists() else []


def load_postgres(cfg: dict, van_ban: list[dict], versions: list[dict], proc: Path, args) -> set[str]:
    from graphrag.storage import postgres

    t0 = time.time()
    conn = postgres.connect(cfg)
    schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    exists = _table_exists(conn, "don_vi")
    if exists and not postgres.don_vi_has_vid(conn) and not args.tao_lai_bang:
        sys.exit("Bảng don_vi đang theo lược đồ cũ (chưa có cột vid). Chạy lại với --tao-lai-bang "
                 "(chỉ xóa bảng don_vi, giữ nhật ký hỏi đáp).")
    postgres.apply_schema(conn, schema, recreate_don_vi=args.tao_lai_bang)
    postgres.clear_data(conn)
    postgres.upsert_van_ban(conn, van_ban)
    postgres.upsert_don_vi(conn, versions)
    print(f"[PostgreSQL] {len(van_ban)} văn bản, {len(versions)} phiên bản")

    emb_path, ids_path = proc / "embedding.npy", proc / "embedding_ids.json"
    if emb_path.exists() and ids_path.exists():
        import numpy as np

        vecs = np.load(emb_path)
        vids = json.load(open(ids_path, encoding="utf-8"))
        known = {r["vid"] for r in versions}
        keep = [i for i, v in enumerate(vids) if v in known]
        thieu = len({r["vid"] for r in versions if r["cap"] != "Chuong"} - set(vids))
        n = postgres.update_embeddings(conn, [vids[i] for i in keep], vecs[keep])
        print(f"[PostgreSQL] embedding: ghi {n} vector ({vecs.shape[1]} chiều)"
              + (f"; {thieu} phiên bản chưa có embedding → chạy lại scripts/03_embed.py" if thieu else ""))
    else:
        print("[PostgreSQL] chưa có embedding.npy → bỏ qua (chạy scripts/03_embed.py rồi nạp lại)")

    s = postgres.summary(conn)
    print(f"[PostgreSQL] {'Văn bản':<12} {'phiên bản':>9} {'đơn vị':>7} {'hết h.lực':>9} {'embedding':>9}")
    for r in s["theo_van_ban"]:
        print(f"             {r['van_ban_id']:<12} {r['phien_ban']:>9} {r['don_vi']:>7} "
              f"{r['da_het_hieu_luc']:>9} {r['co_embedding']:>9}")
    print(f"[PostgreSQL] đang có hiệu lực hôm nay: {s['dang_hieu_luc_hom_nay']} phiên bản · "
          f"dung lượng bảng don_vi: {s['dung_luong_don_vi']} · {time.time() - t0:.1f} giây")
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT id FROM don_vi")
        ids = {r[0] for r in cur.fetchall()}
    conn.close()
    return ids


def _table_exists(conn, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (name,))
        return cur.fetchone()[0]


def load_neo4j(cfg: dict, van_ban: list[dict], versions: list[dict], proc: Path) -> set[str]:
    from graphrag.storage import neo4j_store

    t0 = time.time()
    driver = neo4j_store.connect(cfg)
    driver.verify_connectivity()
    neo4j_store.apply_constraints(driver, (ROOT / "db" / "neo4j_constraints.cypher").read_text(encoding="utf-8"))
    neo4j_store.clear_graph(driver)
    st = neo4j_store.load_structure(driver, versions, van_ban)
    rel = neo4j_store.load_relations(driver, read_jsonl(proc / "references.jsonl"), read_jsonl(proc / "amendments.jsonl"))
    s = neo4j_store.summary(driver)
    driver.close()
    print("[Neo4j] node: " + ", ".join(f"{k} {v}" for k, v in sorted(s["node"].items())))
    print("[Neo4j] cạnh: " + ", ".join(f"{k} {v}" for k, v in sorted(s["canh"].items())))
    print(f"[Neo4j] đã nạp {st['node_don_vi']} mã đơn vị, {sum(rel.values())} cạnh quan hệ · {time.time() - t0:.1f} giây")
    return set(s["ids"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="local", choices=["local", "cloud"])
    ap.add_argument("--chi", choices=["postgres", "neo4j"], help="chỉ nạp một trong hai cơ sở dữ liệu")
    ap.add_argument("--tao-lai-bang", action="store_true", help="xóa và tạo lại bảng don_vi theo db/schema.sql")
    args = ap.parse_args()
    cfg = load_config(args.env)
    proc = ROOT / cfg["paths"]["processed"]
    print(f"Nạp dữ liệu vào môi trường: {cfg['env']}")

    van_ban = list(csv.DictReader(open(ROOT / cfg["paths"]["manifest"], encoding="utf-8-sig")))
    versions = read_jsonl(proc / "versions.jsonl")
    if not versions:
        sys.exit("Chưa có data/processed/versions.jsonl → chạy scripts/02_extract_relations.py trước.")

    pg_ids = load_postgres(cfg, van_ban, versions, proc, args) if args.chi != "neo4j" else None
    neo_ids = load_neo4j(cfg, van_ban, versions, proc) if args.chi != "postgres" else None

    if pg_ids is not None and neo_ids is not None:
        thieu = neo_ids - pg_ids
        print("[Kiểm tra] mọi mã trong Neo4j đều có trong PostgreSQL" if not thieu
              else f"[Kiểm tra] {len(thieu)} mã có trong Neo4j nhưng không có trong PostgreSQL, ví dụ {sorted(thieu)[:5]}")


if __name__ == "__main__":
    main()
