"""Kiểm tra chất lượng corpus.jsonl sau mỗi lần sửa parser.

Phụ trách: TV2 (chạy sau 01_parse.py), TV1 (review).
Chạy:  python scripts/kiem_tra_corpus.py            # in tóm tắt + danh sách lỗi
       python scripts/kiem_tra_corpus.py --chi-tiet # in cả từng dẫn chiếu không giải được

Các phép kiểm tra:
  1. Mã trùng, đơn vị mất cha, nội dung rỗng.
  2. Đánh số liên tục: khoản 1, 2, 3…; điểm a, b, c, d, đ, e… (cho phép khoản chèn 9a).
  3. Nội dung quá dài (có thể bỏ sót ranh giới khoản/điểm) hoặc chứa tiêu đề "Điều N." ở giữa.
  4. Dẫn chiếu nội bộ: "điểm x khoản y Điều này / Điều z" trong văn bản gốc phải trỏ tới mã có thật.
     Dẫn chiếu không giải được thường là dấu hiệu parser đặt sai chữ điểm hoặc số khoản.
Văn bản sửa đổi (vai_tro = sua_doi) chỉ được kiểm tra 1–3, vì dẫn chiếu trong đó trỏ sang văn bản bị sửa.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIET_DIEM = "abcdđeghiklmnopqrstuvxy"
MAX_LEN = {"Diem": 1500, "Khoan": 3000, "Dieu": 6000}

# "điểm a, điểm b và điểm c khoản 2 Điều này", "khoản 3 Điều 6", "điểm đ khoản 1 Điều này"
RE_REF = re.compile(
    r"(?P<diems>(?:điểm\s+[a-zđ](?:\s*,\s*|\s+và\s+|\s+hoặc\s+))*điểm\s+[a-zđ]\s+)?"
    r"khoản\s+(?P<khoan>\d+[a-z]?)\s+"
    r"Điều\s+(?P<dieu>\d+[a-z]?|này)"
    r"(?P<sau>\s+(?:của\s+)?(?:Luật|Nghị định|Thông tư|Bộ luật|Quy chuẩn)[^,;.]{0,40})?"
)
RE_DIEM = re.compile(r"điểm\s+([a-zđ])")
# tên một văn bản khác: "Luật Trật tự…", "Nghị định số 100/2019/NĐ-CP", "của Luật" (không phải "… này")
RE_DOC_KHAC = re.compile(r"(?:Luật|Bộ luật|Nghị định|Thông tư)\s+(?:số\s|[A-ZĐ])|của\s+Luật(?!\s+này)")
RE_HEADING_INSIDE = re.compile(r"\n\s*Điều\s+\d+[a-z]?\.\s")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def vai_tro_map() -> dict[str, str]:
    with open(ROOT / "data/manifest.csv", encoding="utf-8") as f:
        return {r["id"]: r["vai_tro"] for r in csv.DictReader(f)}


def check_structure(units: list[dict]) -> list[str]:
    errs = []
    ids = Counter(u["id"] for u in units)
    errs += [f"[trùng mã] {i} xuất hiện {n} lần" for i, n in ids.items() if n > 1]
    known = set(ids) | {u["van_ban_id"] for u in units}
    for u in units:
        if u["parent_id"] and u["parent_id"] not in known:
            errs.append(f"[mất cha] {u['id']} → {u['parent_id']}")
        if not u["noi_dung"].strip():
            errs.append(f"[rỗng] {u['id']}")
        lim = MAX_LEN.get(u["cap"])
        if lim and len(u["noi_dung"]) > lim and not u.get("co_trich_dan"):
            errs.append(f"[quá dài] {u['id']}: {len(u['noi_dung'])} ký tự")
        if u["cap"] in ("Khoan", "Diem") and RE_HEADING_INSIDE.search(u["noi_dung"]) and not u.get("co_trich_dan"):
            errs.append(f"[tiêu đề lọt vào nội dung] {u['id']}")

    children = defaultdict(list)
    for u in units:
        children[u["parent_id"]].append(u)
    for parent, kids in children.items():
        khoans = [k for k in kids if k["cap"] == "Khoan"]
        nums = [int(re.match(r"\d+", k["so"]).group()) for k in khoans if not re.search(r"[a-z]$", k["so"])]
        if nums and nums != list(range(1, len(nums) + 1)):
            errs.append(f"[khoản không liên tục] {parent}: {nums}")
        diems = [d for d in kids if d["cap"] == "Diem"]
        letters = [d["so"] for d in diems]
        if letters and letters != list(VIET_DIEM[: len(letters)]):
            errs.append(f"[điểm không liên tục] {parent}: {''.join(letters)}")
        for d in diems:
            if d.get("so_goc") and d["so_goc"] != d["so"]:
                errs.append(f"[đã đổi chữ điểm] {d['id']}: văn bản ghi '{d['so_goc']}'")
    return errs


def check_references(units: list[dict], vai_tro: dict[str, str]) -> tuple[int, list[str]]:
    ids = {u["id"] for u in units}
    by_id = {u["id"]: u for u in units}
    total, bad = 0, []
    for u in units:
        if vai_tro.get(u["van_ban_id"]) != "goc" or u.get("co_trich_dan"):
            continue
        # tìm Điều chứa đơn vị này
        dieu_id = u["id"]
        while dieu_id in by_id and by_id[dieu_id]["cap"] not in ("Dieu",):
            dieu_id = by_id[dieu_id]["parent_id"]
        if RE_DOC_KHAC.search(u.get("ngu_canh") or ""):
            continue  # câu dẫn của khoản/điều nói về văn bản khác (vd. "các điều, khoản sau của Luật…")
        text = u["noi_dung"]
        for m in RE_REF.finditer(text):
            if m.group("sau") and "này" not in m.group("sau"):
                continue  # dẫn chiếu sang văn bản khác
            cau = re.split(r"[;:]|\.\s", text[m.end():], maxsplit=1)[0]
            if RE_DOC_KHAC.search(cau):
                continue  # cuối danh sách dẫn chiếu mới ghi tên văn bản khác
            if m.group("dieu") == "này":
                base = dieu_id
            else:
                base = f"{u['van_ban_id']}.D{m.group('dieu')}"
            khoan = f"{base}.K{m.group('khoan')}"
            targets = [f"{khoan}.{x}" for x in RE_DIEM.findall(m.group("diems") or "")] or [khoan]
            for t in targets:
                total += 1
                if t not in ids:
                    bad.append(f"{u['id']}: \"{m.group(0).strip()[:70]}\" → {t} không tồn tại")
    return total, bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "data/processed/corpus.jsonl"))
    ap.add_argument("--chi-tiet", action="store_true")
    args = ap.parse_args()

    units = load(Path(args.corpus))
    errs = check_structure(units)
    total, bad = check_references(units, vai_tro_map())

    groups = Counter(e.split("]")[0] + "]" for e in errs)
    print(f"{len(units)} đơn vị. Lỗi cấu trúc: {len(errs)} {dict(groups)}")
    for e in errs:
        print("  ", e)
    ok = total - len(bad)
    print(f"\nDẫn chiếu nội bộ trong văn bản gốc: {total}, giải được {ok} ({ok / max(total, 1):.1%})")
    for b in bad if args.chi_tiet else bad[:30]:
        print("  ", b)
    if not args.chi_tiet and len(bad) > 30:
        print(f"   ... còn {len(bad) - 30} dòng, chạy với --chi-tiet để xem hết")
    sys.exit(1 if errs or bad else 0)


if __name__ == "__main__":
    main()
