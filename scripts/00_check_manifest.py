"""Kiểm tra data/manifest.csv trước khi chạy các bước sau.

Chạy: python scripts/00_check_manifest.py
Báo: ô bắt buộc còn trống, ngày sai định dạng (phải là YYYY-MM-DD), hiệu lực trước ngày ban hành,
sua_doi_cho trỏ tới mã không có, pham_vi sai cú pháp, file không tồn tại, ngoại lệ hiệu lực sai cú pháp.
"""
from __future__ import annotations

import csv
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from graphrag.common.ids import parse_id  # noqa: E402
from graphrag.parsing.structure_parser import parse_scope  # noqa: E402

BAT_BUOC = ["id", "so_hieu", "ten", "loai", "co_quan", "ngay_ban_hanh", "hieu_luc_tu", "vai_tro", "file"]
VAI_TRO = {"goc", "sua_doi", "doi_chieu"}
RE_NGOAI_LE = re.compile(r"ngoại lệ:\s*(.+)$")


def _date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def main() -> int:
    rows = list(csv.DictReader(open(ROOT / "data" / "manifest.csv", encoding="utf-8-sig")))
    ids = {r["id"] for r in rows}
    loi = 0
    for r in rows:
        msgs = []
        can = BAT_BUOC if r["vai_tro"] != "doi_chieu" else ["id", "so_hieu", "ten", "loai", "file"]
        for c in can:
            if not r.get(c, "").strip():
                msgs.append(f"thiếu {c}")
        for c in ("ngay_ban_hanh", "hieu_luc_tu"):
            if r[c].strip() and not _date(r[c].strip()):
                msgs.append(f"{c}='{r[c]}' sai định dạng YYYY-MM-DD")
        bh, hl = _date(r["ngay_ban_hanh"].strip()), _date(r["hieu_luc_tu"].strip())
        if bh and hl and hl < bh:
            msgs.append("hieu_luc_tu sớm hơn ngay_ban_hanh")
        if r["vai_tro"] not in VAI_TRO:
            msgs.append(f"vai_tro phải thuộc {sorted(VAI_TRO)}")
        if r["vai_tro"] == "sua_doi" and r["sua_doi_cho"] not in ids:
            msgs.append(f"sua_doi_cho='{r['sua_doi_cho']}' không có trong manifest")
        try:
            parse_scope(r["pham_vi"])
        except ValueError as e:
            msgs.append(str(e))
        f = ROOT / "data" / r["file"]
        if not f.exists():
            msgs.append(f"không thấy file data/{r['file']}")
        m = RE_NGOAI_LE.search(r["ghi_chu"])
        if m:
            for part in m.group(1).split(";"):
                uid, _, d = part.strip().partition("=")
                try:
                    parse_id(uid.strip())
                    assert _date(d.strip())
                except (ValueError, AssertionError):
                    msgs.append(f"ngoại lệ hiệu lực sai cú pháp: '{part.strip()}' (đúng: MA_DON_VI=YYYY-MM-DD)")
        if msgs:
            loi += len(msgs)
            print(f"✗ {r['id']}: " + "; ".join(msgs))
        else:
            print(f"✓ {r['id']}")
    print("Manifest hợp lệ." if not loi else f"Còn {loi} lỗi cần sửa.")
    return 1 if loi else 0


if __name__ == "__main__":
    sys.exit(main())
