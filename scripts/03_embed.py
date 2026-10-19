"""Bước 3: tính embedding cho toàn bộ corpus, lưu ra file để bước 4 nạp vào DB.

Phụ trách: TV3.   Chạy: python scripts/03_embed.py
Mặc định gọi baai/bge-m3 qua OpenRouter (configs/base.yaml) → data/processed/embedding.npy (+ embedding_ids.json).
Chỉ cần chạy một lần (hoặc khi corpus thay đổi); local và cloud dùng chung file này.

Văn bản đem mã hóa = ngu_canh + noi_dung (để điểm a), b) mang theo câu dẫn của khoản: mức phạt...).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from graphrag.common.config import load_config  # noqa: E402
from graphrag.embedding import get_embedder  # noqa: E402


def index_text(u: dict) -> str:
    return f"{u['ngu_canh']}\n{u['noi_dung']}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="local", choices=["local", "cloud"])
    args = ap.parse_args()
    cfg = load_config(args.env)

    import numpy as np

    proc = ROOT / cfg["paths"]["processed"]
    units = [json.loads(line) for line in open(proc / "corpus.jsonl", encoding="utf-8")]
    units = [u for u in units if u["cap"] in ("Dieu", "Khoan", "Diem")]
    print(f"Mã hóa {len(units)} đơn vị bằng {cfg['embedding']['provider']}:{cfg['embedding']['model']} ...")
    vecs = get_embedder(cfg).encode_documents([index_text(u) for u in units])

    np.save(proc / "embedding.npy", np.asarray(vecs, dtype=np.float32))
    json.dump([u["id"] for u in units], open(proc / "embedding_ids.json", "w", encoding="utf-8"))
    print(f"{len(units)} vector {cfg['embedding']['dim']} chiều -> {proc / 'embedding.npy'}")


if __name__ == "__main__":
    main()
