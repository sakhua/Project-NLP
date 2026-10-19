"""Tra mã điều khoản trong corpus để ghi gold_ids khi soạn câu hỏi.

  python scripts/tim_dieu_khoan.py "đèn tín hiệu"                    # mọi đơn vị chứa cụm từ
  python scripts/tim_dieu_khoan.py "cao tốc" "120" --van-ban TT38_2024  # chứa đủ các cụm (AND)
  python scripts/tim_dieu_khoan.py --ma ND168_2024.D6.K16             # xem một đơn vị và các con
Tìm không phân biệt hoa thường; thêm --khong-dau để bỏ qua dấu tiếng Việt.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tu_khoa", nargs="*")
    ap.add_argument("--van-ban", help="chỉ tìm trong một văn bản, vd. ND168_2024")
    ap.add_argument("--ma", help="hiện một đơn vị và các đơn vị con")
    ap.add_argument("--khong-dau", action="store_true")
    ap.add_argument("-n", type=int, default=30, help="số kết quả tối đa")
    a = ap.parse_args()
    units = [json.loads(x) for x in open(ROOT / "data/processed/corpus.jsonl", encoding="utf-8")]

    if a.ma:
        for u in units:
            if u["id"] == a.ma or u["id"].startswith(a.ma + "."):
                print(f"{u['id']:26} {u['noi_dung'][:220]}")
        return
    norm = (lambda s: bo_dau(s).lower()) if a.khong_dau else str.lower
    keys = [norm(k) for k in a.tu_khoa]
    found = 0
    for u in units:
        if a.van_ban and u["van_ban_id"] != a.van_ban:
            continue
        text = norm(u["ngu_canh"] + " " + u["noi_dung"])
        if all(k in text for k in keys) and all(k in norm(u["noi_dung"]) or k in norm(u["ngu_canh"]) for k in keys):
            print(f"{u['id']:26} {u['noi_dung'][:200]}")
            found += 1
            if found >= a.n:
                print(f"... (còn nữa, thêm -n hoặc thu hẹp từ khóa)")
                break
    if not found:
        print("Không thấy. Thử ít từ khóa hơn hoặc thêm --khong-dau.")


if __name__ == "__main__":
    main()
