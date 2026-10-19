"""Bước 1: tách các văn bản .docx thành Chương/Điều/Khoản/Điểm -> data/processed/corpus.jsonl

Phụ trách: TV2.   Chạy: python scripts/01_parse.py
Chạy trên máy của nhóm (một lần, hoặc khi parser / manifest thay đổi). Không chạy trên cloud.

Đọc data/manifest.csv: mỗi dòng có file .docx trong data/raw được tách theo cột `pham_vi`
('toan_bo' hoặc 'dieu:7,11'); dòng có vai_tro = doi_chieu bị bỏ qua.
Ghi thêm data/processed/corpus_report.md: số đơn vị theo văn bản và các cảnh báo cần xem tay.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from graphrag.common.config import load_config  # noqa: E402
from graphrag.parsing.structure_parser import parse, parse_scope, write_corpus  # noqa: E402

LOAI_NHAN = {"Luật": "Luật", "Nghị định": "Nghị định", "Thông tư": "Thông tư"}


def main() -> None:
    cfg = load_config()
    raw = ROOT / cfg["paths"]["raw"]
    out_dir = ROOT / cfg["paths"]["processed"]
    out_dir.mkdir(parents=True, exist_ok=True)

    units: list[dict] = []
    report = ["# Báo cáo tách cấu trúc (corpus.jsonl)", "",
              "| Văn bản | Phạm vi | Chương | Điều | Khoản | Điểm | Khối trích dẫn | Bảng | Đánh số tự động | Dừng tại | Cảnh báo |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    warn_sections: list[str] = []
    with open(ROOT / cfg["paths"]["manifest"], encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["vai_tro"] == "doi_chieu":
                continue
            path = raw / f"{row['id']}.docx"
            if not path.exists():
                print(f"!! Không thấy {path}")
                continue
            label = f"{LOAI_NHAN.get(row['loai'], row['loai'])} {row['so_hieu']}"
            res = parse(row["id"], path, parse_scope(row["pham_vi"]), label)
            units += res.units
            s = res.stats
            report.append(f"| {row['id']} | {row['pham_vi'] or 'toan_bo'} | {s['Chuong']} | {s['Dieu']} | {s['Khoan']} "
                          f"| {s['Diem']} | {s['khoi_trich_dan']} | {s['bang']} | {s['danh_so_tu_dong']} "
                          f"| {s['dung_tai'] or '-'} | {len(res.warnings)} |")
            if res.warnings:
                warn_sections += ["", f"## {row['id']}", ""] + [f"- {w}" for w in res.warnings]
            print(f"{row['id']:12} Điều {s['Dieu']:3}  Khoản {s['Khoan']:4}  Điểm {s['Diem']:4}  cảnh báo {len(res.warnings)}")

    ids = [u["id"] for u in units]
    assert len(ids) == len(set(ids)), "Có mã định danh trùng giữa các văn bản"
    write_corpus(units, out_dir / "corpus.jsonl")
    tong = {c: sum(u["cap"] == c for u in units) for c in ("Chuong", "Dieu", "Khoan", "Diem")}
    report += ["", f"**Tổng:** {len(units)} đơn vị — {tong['Chuong']} chương, {tong['Dieu']} điều, "
               f"{tong['Khoan']} khoản, {tong['Diem']} điểm.", "", "# Cảnh báo cần kiểm tra tay"] + warn_sections
    (out_dir / "corpus_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Đã ghi {len(units)} đơn vị -> {out_dir / 'corpus.jsonl'}")


if __name__ == "__main__":
    main()
