"""Bước 4: nạp dữ liệu đã xử lý vào PostgreSQL và Neo4j, rồi kiểm tra đồng bộ mã định danh.

Phụ trách: TV2.
Chạy trên máy của nhóm:
  python scripts/04_load.py               # vào DB local (Docker), đọc .env
  python scripts/04_load.py --env cloud   # lên Supabase + AuraDB, đọc .env.cloud

Đầu vào (tạo bởi các bước 1–3):
  data/manifest.csv                        -> bảng van_ban
  data/processed/corpus.jsonl              -> bảng don_vi + node Neo4j + cạnh THUOC
  data/processed/embedding.npy + embedding_ids.json -> cột don_vi.embedding
  data/processed/references.jsonl          -> cạnh THAM_CHIEU, HUONG_DAN
  data/processed/amendments.jsonl          -> cạnh SUA_DOI / BO_SUNG / THAY_THE / BAI_BO
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graphrag.common.config import load_config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="local", choices=["local", "cloud"])
    args = ap.parse_args()
    cfg = load_config(args.env)
    print(f"Nạp dữ liệu vào môi trường: {cfg['env']}")
    # TODO(TV2):
    # 1. Đọc manifest.csv, ghi bảng van_ban (graphrag.storage.postgres.upsert_van_ban)
    # 2. Đọc corpus.jsonl, ghi bảng don_vi (postgres.upsert_don_vi)
    # 3. Đọc embedding.npy + embedding_ids.json, ghi cột embedding (postgres.update_embeddings)
    # 3b. Gán hieu_luc_tu từ manifest (kể cả "ngoại lệ:" trong ghi_chu) và hieu_luc_den từ amendments.jsonl
    # 4. Tạo node và cạnh THUOC trong Neo4j (graphrag.storage.neo4j_store.load_structure)
    # 5. Tạo cạnh dẫn chiếu, hướng dẫn, sửa đổi (neo4j_store.load_relations)
    # 6. Kiểm tra: mọi mã trong Neo4j đều có trong PostgreSQL; in số node, số cạnh theo loại
    #    (chụp màn hình kết quả này cho báo cáo môn Cloud, bước 5)
    raise NotImplementedError("Hoàn thiện ở tuần 3–5 theo kế hoạch")


if __name__ == "__main__":
    main()
