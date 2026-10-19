"""Kiểm tra file câu hỏi đánh giá theo docs/huong_dan_gan_nhan.md.

  python scripts/check_questions.py data/eval/questions_TV1.jsonl [file khác ...]
Báo lỗi (phải sửa) và cảnh báo (nên xem lại), kèm thống kê tỉ lệ loại câu hỏi.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BAT_BUOC = ["id", "loai", "ngay_ap_dung", "cau_hoi", "dap_an", "so_tien", "diem_tru", "gold_ids", "can_cu",
            "nguoi_soan", "nguon"]
LOAI = {"don": 0.30, "multi_hop": 0.30, "hieu_luc": 0.25, "so_sanh": 0.15}
NGUON = {"tu_viet", "llm_nhap", "vlsp"}
RE_SO_DIEU = re.compile(r"\b(Điều|khoản|điểm)\s+\d", re.IGNORECASE)


def main(paths: list[str]) -> int:
    corpus = {}
    for line in open(ROOT / "data/processed/corpus.jsonl", encoding="utf-8"):
        u = json.loads(line)
        corpus[u["id"]] = u
    qs, loi, canh_bao = [], [], []
    for p in paths:
        for i, line in enumerate(open(p, encoding="utf-8-sig"), 1):
            if not line.strip():
                continue
            try:
                q = json.loads(line)
            except json.JSONDecodeError as e:
                loi.append(f"{p}:{i} JSON sai: {e}")
                continue
            q["_vi_tri"] = f"{p}:{i}"
            qs.append(q)

    ids = Counter(q.get("id") for q in qs)
    by_id = {q.get("id"): q for q in qs}
    for q in qs:
        v = f"{q['_vi_tri']} ({q.get('id')})"
        for f in BAT_BUOC:
            if f not in q:
                loi.append(f"{v}: thiếu trường {f}")
        if ids[q.get("id")] > 1:
            loi.append(f"{v}: id bị trùng")
        if q.get("loai") not in LOAI:
            loi.append(f"{v}: loai phải là một trong {list(LOAI)}")
        if q.get("nguon") not in NGUON:
            loi.append(f"{v}: nguon phải là một trong {sorted(NGUON)}")
        try:
            d = date.fromisoformat(q.get("ngay_ap_dung", ""))
            if not date(2025, 1, 1) <= d <= date(2029, 12, 31):
                canh_bao.append(f"{v}: ngay_ap_dung ngoài khoảng 2025–2029")
        except (TypeError, ValueError):
            loi.append(f"{v}: ngay_ap_dung phải có dạng YYYY-MM-DD")
        if not isinstance(q.get("so_tien"), list) or not all(isinstance(x, int) for x in q.get("so_tien", [])):
            loi.append(f"{v}: so_tien phải là danh sách số nguyên (đồng)")
        if q.get("diem_tru") is not None and not isinstance(q.get("diem_tru"), int):
            loi.append(f"{v}: diem_tru phải là số nguyên hoặc null")
        gold = q.get("gold_ids") or []
        if not gold:
            loi.append(f"{v}: gold_ids rỗng")
        thieu = [g for g in gold if g not in corpus]
        if thieu:
            loi.append(f"{v}: mã không có trong corpus: {thieu}")
        if RE_SO_DIEU.search(q.get("cau_hoi", "")):
            canh_bao.append(f"{v}: câu hỏi có nhắc số điều/khoản/điểm")
        # số tiền phải xuất hiện trong nội dung các gold
        text = " ".join(corpus[g]["ngu_canh"] + " " + corpus[g]["noi_dung"] for g in gold if g in corpus)
        so_trong_vb = {int(x.replace(".", "")) for x in re.findall(r"\d{1,3}(?:\.\d{3})+", text)}
        for t in q.get("so_tien", []) if isinstance(q.get("so_tien"), list) else []:
            if isinstance(t, int) and t not in so_trong_vb:
                canh_bao.append(f"{v}: số tiền {t:,} không thấy trong nội dung các gold".replace(",", "."))
        if q.get("diem_tru") and not re.search(rf"\b0?{q['diem_tru']} điểm", text):
            canh_bao.append(f"{v}: '{q['diem_tru']} điểm' không thấy trong nội dung các gold")
        if q.get("loai") == "hieu_luc":
            cap = by_id.get(q.get("cap_voi"))
            if not cap:
                canh_bao.append(f"{v}: câu hieu_luc nên có cap_voi trỏ tới câu cùng nội dung khác ngày")
            elif cap.get("ngay_ap_dung") == q.get("ngay_ap_dung") or cap.get("dap_an") == q.get("dap_an"):
                canh_bao.append(f"{v}: cặp {q['cap_voi']} phải khác cả ngày áp dụng lẫn đáp án")
        if q.get("loai") == "multi_hop" and len({g.split('.D')[0] + '.D' + g.split('.D')[1].split('.')[0] for g in gold if '.D' in g}) < 2:
            canh_bao.append(f"{v}: multi_hop nhưng gold chỉ thuộc một Điều")

    n = len(qs)
    print(f"Tổng {n} câu.")
    if n:
        dem = Counter(q.get("loai") for q in qs)
        print("Tỉ lệ loại: " + " · ".join(f"{k} {dem.get(k, 0)} ({dem.get(k, 0) / n:.0%}, mục tiêu {t:.0%})"
                                          for k, t in LOAI.items()))
        print("Theo người soạn: " + " · ".join(f"{k} {c}" for k, c in sorted(Counter(q.get('nguoi_soan') for q in qs).items())))
    for m in loi:
        print("LỖI      ", m)
    for m in canh_bao:
        print("CẢNH BÁO ", m)
    print("Không có lỗi." if not loi else f"{len(loi)} lỗi cần sửa.")
    return 1 if loi else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
