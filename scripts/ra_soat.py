"""Hỗ trợ rà soát bộ test tự động (hướng dẫn: docs/Huong_dan_ra_soat_bo_test.pdf).

  python scripts/ra_soat.py tach        # chia data/eval/bo_test_tu_dong.jsonl thành 3 file theo phan_cong
  python scripts/ra_soat.py tien_do     # mỗi người đã rà bao nhiêu câu
  python scripts/ra_soat.py doc_cheo    # chọn câu để đọc chéo, tạo bảng ghi ý kiến data/eval/ra_soat/doc_cheo.csv
  python scripts/ra_soat.py gop         # gộp 3 file đã rà về data/eval/bo_test_tu_dong.jsonl

Mỗi người chỉ sửa file của mình (data/eval/ra_soat/bo_test_TVx.jsonl) nên không bị xung đột khi gộp nhánh Git.
"""
from __future__ import annotations

import csv
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GOC = ROOT / "data/eval/bo_test_tu_dong.jsonl"
THU_MUC = ROOT / "data/eval/ra_soat"
NGUOI = ["TV1", "TV2", "TV3"]
SO_DOC_CHEO = 10          # số câu mỗi người đọc chéo của người khác


def doc(p: Path) -> list[dict]:
    out = []
    for i, line in enumerate(open(p, encoding="utf-8-sig"), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"{p.name} dòng {i}: JSON sai ({e}). Thường do thiếu dấu phẩy hoặc dấu ngoặc kép.")
    return out


def ghi(p: Path, qs: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in qs), encoding="utf-8")


def file_cua(tv: str) -> Path:
    return THU_MUC / f"bo_test_{tv}.jsonl"


def tach() -> None:
    qs = doc(GOC)
    for tv in NGUOI:
        p = file_cua(tv)
        if p.exists():
            sys.exit(f"{p.relative_to(ROOT)} đã có (có thể đã rà dở). Xóa file đó trước nếu muốn chia lại.")
    for tv in NGUOI:
        phan = [q for q in qs if q.get("phan_cong") == tv]
        ghi(file_cua(tv), phan)
        print(f"{tv}: {len(phan)} câu → {file_cua(tv).relative_to(ROOT)}")


def tien_do() -> None:
    for tv in NGUOI:
        p = file_cua(tv)
        if not p.exists():
            print(f"{tv}: chưa có file (chạy 'tach' trước)")
            continue
        c = Counter(q.get("trang_thai", "chua_duyet") for q in doc(p))
        n = sum(c.values())
        xong = n - c.get("chua_duyet", 0)
        print(f"{tv}: {xong}/{n} câu đã rà · đạt {c.get('dat', 0)} · đã sửa {c.get('da_sua', 0)} · "
              f"loại {c.get('loai', 0)} · còn {c.get('chua_duyet', 0)}")


def doc_cheo() -> None:
    """Mỗi người đọc chéo SO_DOC_CHEO câu (đã rà) của người kế tiếp: TV1→TV2, TV2→TV3, TV3→TV1."""
    rng = random.Random(2026)
    rows = []
    for i, tv in enumerate(NGUOI):
        cua = NGUOI[(i + 1) % 3]
        qs = [q for q in doc(file_cua(cua)) if q.get("trang_thai") in ("dat", "da_sua", "loai")]
        chon = sorted(rng.sample(qs, min(SO_DOC_CHEO, len(qs))), key=lambda q: q["id"])
        print(f"{tv} đọc chéo {len(chon)} câu của {cua}: " + ", ".join(q["id"] for q in chon))
        rows += [[q["id"], q["loai"], cua, q.get("trang_thai"), tv, "", "", ""] for q in chon]
    p = THU_MUC / "doc_cheo.csv"
    if p.exists():
        sys.exit(f"{p.relative_to(ROOT)} đã có, không ghi đè (xóa file nếu muốn chọn lại).")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "loai", "nguoi_ra_soat", "ket_luan_nguoi_ra_soat", "nguoi_doc_cheo",
                    "ket_luan_nguoi_doc_cheo (dat/da_sua/loai)", "y_kien", "ket_luan_cuoi"])
        w.writerows(rows)
    print(f"Bảng ghi ý kiến: {p.relative_to(ROOT)} (mở bằng Excel, điền 3 cột cuối)")


def gop() -> None:
    goc = doc(GOC)
    moi = {}
    for tv in NGUOI:
        p = file_cua(tv)
        if not p.exists():
            sys.exit(f"Thiếu {p.relative_to(ROOT)}")
        for q in doc(p):
            if q["id"] in moi:
                sys.exit(f"Câu {q['id']} có trong hai file — kiểm tra lại.")
            moi[q["id"]] = q
    thieu = [q["id"] for q in goc if q["id"] not in moi]
    if thieu:
        sys.exit(f"Các câu sau không có trong file rà soát nào (có thể bị xóa nhầm, hãy đặt trang_thai=loai "
                 f"thay vì xóa): {', '.join(thieu)}")
    them = [i for i in moi if i not in {q['id'] for q in goc}]
    ghi(GOC, [moi[q["id"]] for q in goc] + [moi[i] for i in them])
    print(f"Đã gộp {len(moi)} câu vào {GOC.relative_to(ROOT)}" + (f" (thêm mới: {', '.join(them)})" if them else ""))
    c = Counter(q.get("trang_thai") for q in moi.values())
    print("Trạng thái: " + " · ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda x: str(x[0]))))
    subprocess.run([sys.executable, str(ROOT / "scripts/check_questions.py"), str(GOC)], check=False)


if __name__ == "__main__":
    lenh = {"tach": tach, "tien_do": tien_do, "doc_cheo": doc_cheo, "gop": gop}
    if len(sys.argv) != 2 or sys.argv[1] not in lenh:
        print(__doc__)
        sys.exit(2)
    lenh[sys.argv[1]]()
