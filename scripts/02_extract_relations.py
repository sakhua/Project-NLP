"""Bước 2: dẫn chiếu, thao tác sửa đổi và phiên bản hiệu lực.

Phụ trách: TV1 (viết), TV2 (kiểm tra tay thao tác sửa đổi và 50 dẫn chiếu ngẫu nhiên).
Chạy:  python scripts/02_extract_relations.py
       python scripts/02_extract_relations.py --dung-amendments-co-san   # dùng amendments.jsonl đã sửa tay

Đầu ra (data/processed/):
  amendments.jsonl  thao tác SUA_DOI / THAY_THE / BO_SUNG / BAI_BO        (amendment_parser)
  references.jsonl  cạnh THAM_CHIEU                                      (reference_extractor)
  versions.jsonl    mọi phiên bản Điều/Khoản/Điểm kèm hieu_luc_tu/den   (versioning, TV1) → bước 3 và 4 dùng file này
  versions_report.md  số phiên bản theo văn bản + cảnh báo cần xem tay

Sau khi sửa amendments.jsonl bằng tay (kiểm tra thao tác sai), chạy lại với --dung-amendments-co-san
để giữ phần đã sửa.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from graphrag.common.config import load_config  # noqa: E402
from graphrag.parsing import amendment_parser, reference_extractor  # noqa: E402
from graphrag.parsing.versioning import build_versions, load_manifest, ngay_hieu_luc_thao_tac  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8")] if path.exists() else []


def write_jsonl(rows: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dung-amendments-co-san", action="store_true",
                    help="đọc amendments.jsonl hiện có (đã kiểm tra, sửa tay) thay vì chạy lại amendment_parser")
    args = ap.parse_args()
    cfg = load_config()
    proc = ROOT / cfg["paths"]["processed"]
    manifest_path = ROOT / cfg["paths"]["manifest"]
    units = read_jsonl(proc / "corpus.jsonl")
    notes: list[str] = []

    manifest_rows = list(csv.DictReader(open(manifest_path, encoding="utf-8-sig")))
    manifest = load_manifest(manifest_path)
    vai_tro = {r["id"]: r["vai_tro"] for r in manifest_rows}

    # 1. Thao tác sửa đổi (văn bản sửa đổi xếp theo ngày hiệu lực: TT13 trước TT105, NĐ 184 trước NĐ 236…)
    if args.dung_amendments_co_san:
        amendments = read_jsonl(proc / "amendments.jsonl")
    else:
        pairs = sorted([(r["id"], r["sua_doi_cho"]) for r in manifest_rows if r["vai_tro"] == "sua_doi" and r["sua_doi_cho"]],
                       key=lambda p: manifest[p[0]].hieu_luc_tu or date.max)
        amendments, warn_a = amendment_parser.parse_all(units, pairs)
        notes += [f"[sửa đổi] {w}" for w in warn_a]
    for op in amendments:                      # ghi ngày hiệu lực đã tính (R2) để bước 4 gắn lên cạnh Neo4j
        if not op.get("ngay_hieu_luc"):
            d = ngay_hieu_luc_thao_tac(manifest, op)
            op["ngay_hieu_luc"] = d.isoformat() if d else None
    write_jsonl(amendments, proc / "amendments.jsonl")

    # 2. Phiên bản
    rows, warnings = build_versions(units, amendments, manifest)
    write_jsonl(rows, proc / "versions.jsonl")

    # 3. Dẫn chiếu: quét mọi phiên bản của văn bản gốc (nội dung mới sau sửa đổi cũng có dẫn chiếu)
    known = {r["id"] for r in rows}
    by_id = {u["id"]: u for u in units}
    refs: list[dict] = []
    seen: set[tuple] = set()
    for r in rows:
        if vai_tro.get(r["van_ban_id"]) != "goc":
            continue
        ctx = r.get("ngu_canh") or ""
        dieu = by_id.get(r["id"].split(".K")[0]) if ".K" in r["id"] else None
        if dieu and (dieu.get("tieu_de") or "").startswith("Phạm vi điều chỉnh"):
            ctx += "\n" + dieu["noi_dung"]
        for e in reference_extractor.find_references(r["noi_dung"], r["id"], known, ctx):
            key = (e["src"], e["dst"], e["text"] if e["dst"] is None else "")
            if key not in seen:
                seen.add(key)
                refs.append(e)
    write_jsonl(refs, proc / "references.jsonl")
    n_ok = sum(1 for e in refs if e["dst"] and not e.get("khong_ton_tai"))

    by_doc = Counter((r["van_ban_id"], r["loai_phien_ban"]) for r in rows)
    docs = list(dict.fromkeys(r["van_ban_id"] for r in rows))
    lines = ["# Phiên bản hiệu lực (versions.jsonl)", "",
             f"{len(units)} đơn vị gốc, {len(amendments)} thao tác sửa đổi → {len(rows)} phiên bản.",
             f"Dẫn chiếu: {len(refs)}, giải được {n_ok}, ngoài kho {sum(1 for e in refs if e.get('ngoai_pham_vi'))}, "
             f"trỏ tới mã không có {sum(1 for e in refs if e.get('khong_ton_tai'))}.", "",
             "| Văn bản | Bản gốc | Sửa đổi | Thay thế | Bổ sung | Đã hết hiệu lực |", "|---|---|---|---|---|---|"]
    for d in docs:
        het = sum(1 for r in rows if r["van_ban_id"] == d and r["hieu_luc_den"])
        lines.append(f"| {d} | {by_doc[(d, 'goc')]} | {by_doc[(d, 'sua_doi')]} | {by_doc[(d, 'thay_the')]} "
                     f"| {by_doc[(d, 'bo_sung')]} | {het} |")
    lines += ["", "## Ghi chú", ""] + [f"- {n}" for n in notes]
    lines += ["", "## Cảnh báo cần kiểm tra tay", ""] + [f"- {w}" for w in warnings]
    (proc / "versions_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{len(amendments)} thao tác sửa đổi, {len(rows)} phiên bản, {n_ok} dẫn chiếu "
          f"-> {proc}  ({len(warnings) + len(notes)} cảnh báo, xem versions_report.md)")


if __name__ == "__main__":
    main()
