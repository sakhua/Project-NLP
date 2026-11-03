"""Sinh bộ câu hỏi chạy thử tự động từ dữ liệu đã xử lý (KHÔNG phải bộ đánh giá chính thức).

  python scripts/sinh_bo_test.py                     # → data/eval/bo_test_tu_dong.jsonl (200 câu)
  python scripts/sinh_bo_test.py --so-cau 100 --seed 7

Mục đích: có ngay một bộ câu đủ lớn để xem hệ thống đang chạy ra sao, trong lúc nhóm soạn bộ câu chính thức
theo docs/huong_dan_gan_nhan.md.

Cách sinh (không dùng LLM, không tự "nghĩ" đáp án):
  - Mức tiền, số điểm trừ, mã gold đều đọc thẳng từ data/processed/versions.jsonl, lấy đúng phiên bản có hiệu lực
    vào ngày áp dụng của câu hỏi. Câu hỏi được ghép từ chính câu chữ của điểm/khoản (đã lược phần dẫn chiếu).
  - don        : một hành vi trong NĐ 168/2024 → mức phạt (gold = mã điểm/khoản chứa hành vi).
  - multi_hop  : (1) hành vi có trừ điểm GPLX → cần cả khoản mức phạt và khoản trừ điểm (nối qua THAM_CHIEU);
                 (2) chạy X km/h trên loại đường Y → tra tốc độ tối đa ở TT 38/2024 rồi mức phạt ở NĐ 168/2024.
  - hieu_luc   : cặp câu giống nhau, khác ngày, trước/sau một mốc hiệu lực hoặc sửa đổi (NĐ 238/2026…).
  - so_sanh    : cùng một hành vi, ô tô và xe máy (hoặc xe máy và xe đạp) bị phạt khác nhau thế nào.

Hạn chế cần biết khi đọc kết quả:
  - Câu hỏi dùng lại câu chữ của văn bản nên dễ hơn câu hỏi đời thường (BM25 có lợi). Bộ chính thức do người viết.
  - Câu hieu_luc "trước mốc bổ sung" giả định hành vi chưa bị xử phạt ở quy định khác; xem ghi_chu từng câu.
  - dap_an chỉ nêu mức tiền và điểm trừ, không nêu hình thức bổ sung (tước GPLX, tịch thu…).
"""
from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ND = "ND168_2024"
NGAY = "2026-10-15"          # ngày áp dụng mặc định (sau khi NĐ 238/2026 có hiệu lực)
NGAY_CU = "2025-06-01"       # một phần câu đơn hỏi ở ngày cũ nếu nội dung không đổi

TEN_VB = {"ND168_2024": "NĐ 168/2024", "TT38_2024": "TT 38/2024", "ND238_2026": "NĐ 238/2026", "L36_2024": "Luật 36/2024"}

# Chủ thể theo Điều của NĐ 168/2024 (None: câu chữ của hành vi đã nêu chủ thể)
CHU_THE = {6: "lái ô tô", 7: "đi xe máy", 9: "đi xe đạp", 10: "người đi bộ", 13: "lái ô tô", 14: "đi xe máy",
           12: None, 18: None, 33: "hành khách đi xe"}
DIEU_DON = [6, 7, 9, 10, 12, 13, 14, 18, 33]

RE_TIEN = re.compile(r"^Phạt tiền từ ([\d\.]+) đồng đến ([\d\.]+) đồng đối với (.*)$", re.S)
RE_CA_NHAN = re.compile(r"^cá nhân, từ [\d\.]+ (?:đồng )?đến [\d\.]+ đồng đối với tổ chức (.*)$", re.S)
RE_TRU = re.compile(r"trừ điểm giấy phép lái xe (\d+) điểm")
RE_THAM_CHIEU = re.compile(r"điểm\s+([a-zđ]\d?)|khoản\s+(\d+[a-z]?)")
LEAD_CHUNG = re.compile(r"^(?:người điều khiển xe |người đi bộ |cá nhân |người )?(?:thực hiện )?một trong các hành vi")


# ---------------------------------------------------------------- dữ liệu

class Kho:
    def __init__(self) -> None:
        self.by: dict[str, list[dict]] = defaultdict(list)
        self.children: dict[str, list[str]] = defaultdict(list)
        for line in open(ROOT / "data/processed/versions.jsonl", encoding="utf-8"):
            v = json.loads(line)
            if not self.by[v["id"]]:
                self.children[v["parent_id"]].append(v["id"])
            self.by[v["id"]].append(v)

    def ver(self, uid: str, ngay: str) -> dict | None:
        for v in self.by.get(uid, []):
            if v["hieu_luc_tu"] <= ngay and (v["hieu_luc_den"] is None or ngay < v["hieu_luc_den"]):
                return v
        return None

    def con(self, uid: str, ngay: str) -> list[dict]:
        return [v for c in self.children.get(uid, []) if (v := self.ver(c, ngay))]


def tien(s: str) -> int:
    return int(s.replace(".", ""))


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def fmt_khoang(a: int, b: int) -> str:
    return f"{fmt(a)}–{fmt(b)} đồng"


def can_cu(uid: str) -> str:
    """ND168_2024.D6.K9.b → 'điểm b khoản 9 Điều 6 NĐ 168/2024'."""
    vb, *rest = uid.split(".")
    parts = {"D": "Điều", "K": "khoản"}
    out = []
    for r in reversed(rest):
        if r[0] in parts and r[1:2].isdigit():
            out.append(f"{parts[r[0]]} {r[1:]}")
        else:
            out.append(f"điểm {r}")
    return " ".join(out) + " " + TEN_VB.get(vb, vb)


def ngay_vn(s: str) -> str:
    d = date.fromisoformat(s)
    return d.strftime("%d/%m/%Y")


# ---------------------------------------------------------------- hành vi + mức phạt

def lam_sach(t: str) -> str | None:
    """Câu chữ của điểm → cụm hành vi dùng trong câu hỏi. None nếu không dùng được."""
    t = t.strip()
    t = t.split(";")[0].strip() if ";" in t and len(t.split(";")[0]) >= 20 else t
    t = re.sub(r",?\s*trừ (?:các |trường hợp |hành vi )[^;]*?quy định tại[^;]*$", "", t)
    t = re.sub(r"\s*\([^()]*quy định tại[^()]*\)", "", t)
    t = t.rstrip(" ;.,:")
    if re.search(r"quy định tại|Điều này|khoản \d|điểm [a-zđ]\b", t) or not 15 <= len(t) <= 170:
        return None
    return t[0].lower() + t[1:]


def bo_dong_tu(beh: str) -> str:
    """'điều khiển xe chạy quá tốc độ…' → 'chạy quá tốc độ…' (chủ thể đã nằm trong câu hỏi)."""
    h = re.sub(r"^điều khiển (?:xe (?:ô tô|mô tô, xe gắn máy|mô tô|gắn máy|đạp, xe đạp máy|đạp)\s*|xe\s+|phương tiện\s+)?",
               "", beh)
    h = re.sub(r"^trên đường mà\s+", "", h)
    h = re.sub(r"^người đang điều khiển xe (?!hoặc)", "", h)
    h = re.sub(r"^xe không được quyền ưu tiên\s+", "", h)
    return h


# Sau khi bỏ "điều khiển xe", phần còn lại phải bắt đầu bằng động từ thì mới ghép được "Lái ô tô mà …"
DONG_TU = re.compile(r"^(?:chạy|đi|dừng|đỗ|lùi|quay|vượt|chuyển|tránh|không|bám|kéo|lắp|sử dụng|để|thành đoàn|dàn hàng|"
                     r"buông|bằng|vào|ra|có liên quan|liên quan|bấm|rú|lạng|đua|thả|mở|tháo|dùng|gây|chở|trong|"
                     r"mang|ngồi|đeo|dán|gắn|đăng ký|có|cho|đón|xếp|khi|tại|sau|trước)\b")
TEN_XE = {6: "xe ô tô", 13: "xe ô tô", 7: "xe máy", 14: "xe máy", 9: "xe đạp"}


def ghep_chu_the(hv: dict) -> tuple[str | None, str]:
    """(chủ thể, cụm hành vi) để ghép câu hỏi; chủ thể None thì cụm hành vi tự đứng đầu câu."""
    beh = hv["hanh_vi"]
    if not hv["chu_the"]:
        return None, beh
    if re.match(r"điều khiển xe (?:chở người|chở hàng) bốn bánh", beh):
        return None, beh
    h = bo_dong_tu(beh)
    if beh.startswith("điều khiển") and not DONG_TU.match(h):
        # "điều khiển xe kinh doanh vận tải có niên hạn…" → giữ nguyên, thêm loại xe
        if hv["dieu"] in TEN_XE and re.match(r"điều khiển xe (?!ô tô|mô tô|gắn máy|đạp)", beh):
            beh = beh.replace("điều khiển xe", "điều khiển " + TEN_XE[hv["dieu"]], 1)
        return None, beh
    return hv["chu_the"], h


def hanh_vi_trong_dieu(kho: Kho, dieu: int, ngay: str) -> list[dict]:
    """Mọi hành vi có mức phạt tiền trong một Điều của NĐ 168/2024 tại ngày áp dụng."""
    out = []
    for k in kho.con(f"{ND}.D{dieu}", ngay):
        if k["cap"] != "Khoan":
            continue
        m = RE_TIEN.match(k["noi_dung"].strip())
        if not m:
            continue
        a, b, rest = tien(m.group(1)), tien(m.group(2)), m.group(3).strip()
        chu_the = CHU_THE.get(dieu)
        ca_nhan = RE_CA_NHAN.match(rest)
        if ca_nhan:
            rest, chu_the = ca_nhan.group(1), "cá nhân"
        elif rest.startswith("cá nhân "):
            rest, chu_the = rest[len("cá nhân "):], "cá nhân"
        diem = [d for d in kho.con(k["id"], ngay) if d["cap"] == "Diem"]
        if diem and LEAD_CHUNG.search(rest + " "):
            for d in diem:
                beh = lam_sach(d["noi_dung"])
                if beh:
                    ct = None if re.match(r"(?:người|chủ)\b(?! đang điều khiển xe (?!hoặc))", beh) else chu_the
                    out.append({"id": d["id"], "khoan": k["id"], "tien": [a, b], "hanh_vi": beh, "chu_the": ct,
                                "dieu": dieu, "goc": d["noi_dung"]})
        elif not diem:
            rest = re.sub(r"^(?:thực hiện )?hành vi (?:vi phạm )?", "", rest)
            beh = lam_sach(rest)
            if beh:
                # lead-in tự nêu chủ thể ("người được chở trên xe ô tô…") thì không thêm chủ thể
                tu_neu = bool(re.match(r"(?:người|chủ|cá nhân|tổ chức)\b", beh))
                out.append({"id": k["id"], "khoan": k["id"], "tien": [a, b], "hanh_vi": beh,
                            "chu_the": None if tu_neu else chu_the, "dieu": dieu, "goc": rest})
    return out


def tru_diem(kho: Kho, dieu: int, ngay: str) -> dict[str, tuple[int, str]]:
    """mã hành vi → (số điểm trừ, mã đơn vị quy định trừ điểm), đọc từ câu chữ 'bị trừ điểm … NN điểm'."""
    out: dict[str, tuple[int, str]] = {}
    units = []
    for k in kho.con(f"{ND}.D{dieu}", ngay):
        units.append(k)
        units += kho.con(k["id"], ngay)
    for u in units:
        m = RE_TRU.search(u["noi_dung"])
        if not m:
            continue
        ref = u["noi_dung"][:m.start()]
        if re.search(r"Điều \d", ref):
            continue
        n, pending = int(m.group(1)), []
        for dm, km in RE_THAM_CHIEU.findall(ref):
            if dm:
                pending.append(dm)
                continue
            kid = f"{ND}.D{dieu}.K{km}"
            targets = [f"{kid}.{p}" for p in pending] if pending else \
                [kid] + [c["id"] for c in kho.con(kid, ngay)]
            pending = []
            for t in targets:
                out.setdefault(t, (n, u["id"]))
    return out


# ---------------------------------------------------------------- mẫu câu hỏi

MAU_DON = [
    "{S} mà {h} thì bị phạt bao nhiêu tiền?",
    "{S} {h} sẽ bị xử phạt như thế nào?",
    "Mức phạt khi {s} {h} là bao nhiêu?",
]
MAU_DON_KHONG_CHU = [
    "{H} thì bị phạt bao nhiêu tiền?",
    "Trường hợp {h} bị xử phạt như thế nào?",
]
MAU_TRU = [
    "{S} mà {h} thì bị phạt bao nhiêu tiền, có bị trừ điểm giấy phép lái xe không?",
    "{S} {h} bị xử phạt thế nào và bị trừ mấy điểm giấy phép lái xe?",
]
MAU_TRU_KHONG_CHU = [
    "{H} thì bị phạt bao nhiêu và bị trừ mấy điểm giấy phép lái xe?",
]


def cau_hoi(hv: dict, mau: list[str], mau_kc: list[str], rng: random.Random) -> str:
    s, h = ghep_chu_the(hv)
    if s:
        return rng.choice(mau).format(S=s[0].upper() + s[1:], s=s, h=h)
    return rng.choice(mau_kc).format(H=h[0].upper() + h[1:], h=h)


def q(loai, ngay, cau, dap_an, so_tien, diem, gold, cc, ghi_chu="", **kw) -> dict:
    d = {"id": "", "loai": loai, "ngay_ap_dung": ngay, "cau_hoi": cau, "dap_an": dap_an, "so_tien": so_tien,
         "diem_tru": diem, "gold_ids": gold, "can_cu": cc, "nguoi_soan": "tu_dong", "nguon": "tu_dong"}
    d.update(kw)
    d["ghi_chu"] = ("Sinh tự động bởi scripts/sinh_bo_test.py, chưa có người duyệt. " + ghi_chu).strip()
    return d


# ---------------------------------------------------------------- 4 loại

LUOC = ("RÀ SOÁT: câu chữ gốc có phần loại trừ 'trừ … quy định tại …' đã bị lược khỏi câu hỏi; "
        "kiểm tra tình huống trong câu hỏi không rơi vào trường hợp bị loại trừ (nếu có thì sửa câu hỏi cho hẹp lại).")


def chu_y(hv: dict) -> str:
    return LUOC if "quy định tại" in hv["goc"] else ""


def sinh_don_va_multi(kho: Kho, rng: random.Random) -> tuple[list[dict], list[dict]]:
    don, multi = [], []
    for dieu in DIEU_DON:
        tru = tru_diem(kho, dieu, NGAY)
        for hv in hanh_vi_trong_dieu(kho, dieu, NGAY):
            t = tru.get(hv["id"]) or tru.get(hv["khoan"])
            a, b = hv["tien"]
            tien_txt = f"Phạt tiền {fmt_khoang(a, b)}" + (" (mức áp dụng với cá nhân)" if hv["chu_the"] == "cá nhân" else "")
            if t:
                n, tid = t
                multi.append(q("multi_hop", NGAY, cau_hoi(hv, MAU_TRU, MAU_TRU_KHONG_CHU, rng),
                               f"{tien_txt} và bị trừ {n} điểm giấy phép lái xe.", [a, b], n, [hv["id"], tid],
                               f"{can_cu(hv['id'])}; {can_cu(tid)}", chu_y(hv), _dieu=dieu))
            else:
                ngay = NGAY
                # một phần câu hỏi ở ngày cũ, nếu nội dung hành vi và mức tiền không đổi
                if rng.random() < 0.25:
                    cu, cu_k = kho.ver(hv["id"], NGAY_CU), kho.ver(hv["khoan"], NGAY_CU)
                    moi, moi_k = kho.ver(hv["id"], NGAY), kho.ver(hv["khoan"], NGAY)
                    if cu and cu_k and cu["noi_dung"] == moi["noi_dung"] and cu_k["noi_dung"] == moi_k["noi_dung"]:
                        ngay = NGAY_CU
                don.append(q("don", ngay, cau_hoi(hv, MAU_DON, MAU_DON_KHONG_CHU, rng), f"{tien_txt}.",
                             [a, b], None, [hv["id"]], can_cu(hv["id"]), chu_y(hv), _dieu=dieu))
    return don, multi


# Tốc độ tối đa (TT 38/2024) khi không có biển báo riêng: (mô tả đường, mã căn cứ, ô tô 5 chỗ, xe mô tô)
DUONG = [
    ("trên đường đôi (có dải phân cách giữa) trong khu đông dân cư", "TT38_2024.D6.K1", 60, 60),
    ("trên đường hai chiều không có dải phân cách trong khu đông dân cư", "TT38_2024.D6.K1", 50, 50),
    ("trên đường đôi (có dải phân cách giữa) ngoài khu đông dân cư", "TT38_2024.D6.K2", 90, 70),
    ("trên đường hai chiều không có dải phân cách ngoài khu đông dân cư", "TT38_2024.D6.K2", 80, 60),
    ("trên đường cao tốc", "TT38_2024.D9.K2", 120, None),
]
# vượt bao nhiêu km/h → (điểm phạt ô tô, điểm phạt xe máy)
MUC_VUOT = [(7, "ND168_2024.D6.K3.a", "ND168_2024.D7.K2.b"), (15, "ND168_2024.D6.K5.đ", "ND168_2024.D7.K4.a"),
            (28, "ND168_2024.D6.K6.a", "ND168_2024.D7.K8.a"), (40, "ND168_2024.D6.K7.a", None)]


def sinh_toc_do(kho: Kho) -> list[dict]:
    out = []
    tru6, tru7 = tru_diem(kho, 6, NGAY), tru_diem(kho, 7, NGAY)
    for mo_ta, tt, oto, xm in DUONG:
        for vuot, p6, p7 in MUC_VUOT:
            for xe, gioi_han, pid, tru in (("Xe ô tô 5 chỗ", oto, p6, tru6), ("Xe máy (xe mô tô)", xm, p7, tru7)):
                if not gioi_han or not pid:
                    continue
                if xe.startswith("Xe máy") and vuot == 28:
                    vuot_thuc = 25
                else:
                    vuot_thuc = vuot
                k = kho.ver(pid.rsplit(".", 1)[0], NGAY)
                m = RE_TIEN.match(k["noi_dung"])
                a, b = tien(m.group(1)), tien(m.group(2))
                t = tru.get(pid)
                gold = [tt, pid] + ([t[1]] if t else [])
                v = gioi_han + vuot_thuc
                dap = (f"Tốc độ tối đa cho phép là {gioi_han} km/h nên xe chạy quá {vuot_thuc} km/h: phạt tiền "
                       f"{fmt_khoang(a, b)}" + (f" và bị trừ {t[0]} điểm giấy phép lái xe." if t else "."))
                out.append(q("multi_hop", NGAY, f"{xe} chạy {v} km/h {mo_ta} thì bị xử phạt thế nào?", dap,
                             [a, b], t[0] if t else None, gold,
                             "; ".join(can_cu(g) for g in gold),
                             "Giả định đoạn đường không có biển báo tốc độ riêng; ô tô 5 chỗ thuộc nhóm xe chở người đến 28 chỗ."))
    return out


def sinh_so_sanh(kho: Kho, rng: random.Random) -> list[dict]:
    out = []
    cap = [(6, 7, "người lái ô tô", "người đi xe máy"), (7, 9, "người đi xe máy", "người đi xe đạp")]
    for d1, d2, t1, t2 in cap:
        h1, h2 = hanh_vi_trong_dieu(kho, d1, NGAY), hanh_vi_trong_dieu(kho, d2, NGAY)
        tr1, tr2 = tru_diem(kho, d1, NGAY), tru_diem(kho, d2, NGAY)
        dung = set()
        for a in h1:
            ba = bo_dong_tu(a["hanh_vi"])
            best, r = None, 0.0
            for b in h2:
                if b["id"] in dung:
                    continue
                rb = difflib.SequenceMatcher(None, ba, bo_dong_tu(b["hanh_vi"])).ratio()
                if rb > r:
                    best, r = b, rb
            if not best or r < 0.88 or a["tien"] == best["tien"]:
                continue
            dung.add(best["id"])
            x1 = tr1.get(a["id"]) or tr1.get(a["khoan"])
            x2 = tr2.get(best["id"]) or tr2.get(best["khoan"])
            gold = [a["id"], best["id"]] + [x[1] for x in (x1, x2) if x]

            def mo_ta(hv, x, ten):
                s = f"{ten[0].upper() + ten[1:]}: phạt tiền {fmt_khoang(*hv['tien'])}"
                return s + (f", trừ {x[0]} điểm giấy phép lái xe" if x else "")

            dap = mo_ta(a, x1, t1) + ". " + mo_ta(best, x2, t2) + "."
            diem = x1[0] if x1 and x2 and x1[0] == x2[0] else None
            hv = bo_dong_tu(a["hanh_vi"])
            cau = rng.choice([f"Cùng lỗi {hv}, {t1} và {t2} bị phạt khác nhau thế nào?",
                              f"So sánh mức phạt giữa {t1} và {t2} khi {hv}."])
            ghi = (f"RÀ SOÁT: hai hành vi được ghép tự động theo độ giống câu chữ ({r:.2f}); đọc cả hai điểm "
                   f"để chắc chắn là cùng một lỗi. " + chu_y(a) + (" " + chu_y(best) if chu_y(best) and not chu_y(a) else ""))
            out.append(q("so_sanh", NGAY, cau, dap, a["tien"] + best["tien"], diem, gold,
                         "; ".join(can_cu(g) for g in gold), ghi.strip()))
    return out


def sinh_hieu_luc(kho: Kho) -> list[dict]:
    """Cặp câu trước/sau mốc hiệu lực. Mỗi cặp: (câu trước, câu sau)."""
    cap: list[tuple[dict, dict]] = []

    def tien_khoan(uid, ngay):
        v = kho.ver(uid, ngay)
        m = RE_TIEN.match(v["noi_dung"]) if v else None
        return (tien(m.group(1)), tien(m.group(2))) if m else None

    # 1) Thẩm quyền phạt tiền thay đổi theo NĐ 238/2026 (cùng chức danh, khác mức)
    tham_quyen = [
        ("Chủ tịch Ủy ban nhân dân cấp xã", "ND168_2024.D42.K1.b", "ND168_2024.D42.K1.b"),
        ("Chiến sĩ Công an nhân dân đang thi hành công vụ", "ND168_2024.D43.K1.b", "ND168_2024.D43.K1.b"),
        ("Trưởng Công an cấp xã", "ND168_2024.D43.K3.b", "ND168_2024.D43.K4.b"),
    ]
    for ten, id_cu, id_moi in tham_quyen:
        ngay1, ngay2 = "2026-05-01", "2026-10-01"
        v1, v2 = kho.ver(id_cu, ngay1), kho.ver(id_moi, ngay2)
        k1, k2 = kho.ver(id_cu.rsplit(".", 1)[0], ngay1), kho.ver(id_moi.rsplit(".", 1)[0], ngay2)
        if not (v1 and v2 and ten in k1["noi_dung"] and ten in k2["noi_dung"]):
            continue
        s1 = tien(re.search(r"([\d\.]{5,}) đồng", v1["noi_dung"]).group(1))
        s2 = tien(re.search(r"([\d\.]{5,}) đồng", v2["noi_dung"]).group(1))
        cau = f"{ten} được phạt tiền tối đa bao nhiêu đối với vi phạm giao thông đường bộ?"
        cap.append((
            q("hieu_luc", ngay1, cau, f"Phạt tiền đến {fmt(s1)} đồng.", [s1], None, [id_cu], can_cu(id_cu),
              so_tien_khong_duoc_co=[s2]),
            q("hieu_luc", ngay2, cau, f"Phạt tiền đến {fmt(s2)} đồng (theo quy định đã được NĐ 238/2026 sửa đổi).",
              [s2], None, [id_moi], can_cu(id_moi), nguon_sua_doi=[v2["nguon_sua_doi"]],
              so_tien_khong_duoc_co=[s1]),
        ))

    # 2) Câu hỏi viết tay cho các mốc hiệu lực muộn (Điều 53) và nội dung bổ sung/sửa đổi có hiệu lực 2028–2029.
    #    Câu chữ câu hỏi do người/LLM viết; mức tiền, mã gold, mốc ngày vẫn đọc từ dữ liệu.
    #    (mã điểm, ngày trước, ngày sau, câu hỏi, mã điều khoản quy định mốc hiệu lực, áp dụng cho cá nhân?)
    viet_tay = [
        ("ND168_2024.D6.K3.m", "2025-10-01", "2026-03-01",
         "Lái ô tô cho con 7 tuổi, cao 1,2 m ngồi ghế phụ phía trước thì bị phạt bao nhiêu tiền?", "ND168_2024.D53.K2", False),
        ("ND168_2024.D27.K1.b", "2025-10-01", "2026-03-01",
         "Tài xế xe đưa đón học sinh tiểu học mà trên xe không có ghế ngồi phù hợp với lứa tuổi thì bị phạt bao nhiêu?",
         "ND168_2024.D53.K2", False),
        ("ND168_2024.D26.K4.e", "2025-10-01", "2026-03-01",
         "Cá nhân kinh doanh vận tải dùng ô tô đưa đón trẻ mầm non mà xe không có dây đai an toàn phù hợp lứa tuổi "
         "thì bị phạt bao nhiêu?", "ND168_2024.D53.K2", True),
        ("ND168_2024.D20.K5.l", "2027-06-01", "2028-03-01",
         "Lái xe 4 chỗ kinh doanh vận tải hành khách mà xe không lắp camera ghi hình người lái xe thì bị phạt bao nhiêu?",
         "ND168_2024.D53.K3", False),
        ("ND168_2024.D21.K3.b", "2027-06-01", "2028-03-01",
         "Lái xe tải kinh doanh vận tải hàng hóa (không phải xe đầu kéo) mà xe không lắp camera ghi hình người lái xe "
         "thì bị phạt bao nhiêu?", "ND168_2024.D53.K3", False),
        ("ND168_2024.D32.K9a.b", "2027-06-01", "2028-03-01",
         "Chủ xe vận tải nội bộ là cá nhân đưa xe không lắp camera ghi hình người lái xe ra hoạt động thì bị phạt bao nhiêu?",
         "ND168_2024.D53.K3", True),
        ("ND168_2024.D20.K5.n", "2028-06-01", "2029-03-01",
         "Lái xe khách 16 chỗ kinh doanh vận tải mà xe không lắp camera ghi hình khoang chở khách thì bị phạt bao nhiêu?",
         "ND168_2024.D53.K4", False),
        ("ND168_2024.D26.K7.k", "2028-06-01", "2029-03-01",
         "Cá nhân kinh doanh vận tải hành khách dùng xe 29 chỗ không lắp camera ghi hình khoang chở khách thì bị phạt bao nhiêu?",
         "ND168_2024.D53.K4", True),
        ("ND168_2024.D32.K9a.a", "2026-06-01", "2026-10-01",
         "Chủ xe vận tải nội bộ là cá nhân đưa xe không lắp thiết bị giám sát hành trình ra hoạt động thì bị phạt bao nhiêu?",
         None, True),
        ("ND168_2024.D26.K8.d", "2026-06-01", "2026-10-01",
         "Cá nhân kinh doanh xe chạy hợp đồng mà bán vé, thu tiền của từng hành khách ngoài hợp đồng đã ký thì bị phạt bao nhiêu?",
         None, True),
    ]
    da_viet = {x[0] for x in viet_tay}
    for uid, ngay1, ngay2, cau, moc_id, ca_nhan in viet_tay:
        v2 = kho.ver(uid, ngay2)
        tk = tien_khoan(uid.rsplit(".", 1)[0], ngay2)
        if not (v2 and tk):
            print("  bỏ qua (không có dữ liệu):", uid)
            continue
        moc = v2["hieu_luc_tu"] if v2["loai_phien_ban"] != "goc" or moc_id else v2["hieu_luc_tu"]
        if moc_id:
            moc = re.search(r"từ ngày (\d+) tháng (\d+) năm (\d{4})", kho.ver(moc_id, ngay2)["noi_dung"])
            moc = f"{int(moc.group(1)):02d}/{int(moc.group(2)):02d}/{moc.group(3)}" if moc else ngay_vn(v2["hieu_luc_tu"])
        else:
            moc = ngay_vn(v2["hieu_luc_tu"])
        gold1 = [uid] + ([moc_id] if moc_id else [])
        cc1 = can_cu(uid) + (f"; {can_cu(moc_id)}" if moc_id else "")
        nsd = [v2["nguon_sua_doi"]] if v2.get("nguon_sua_doi") else []
        ghi = "" if moc_id else "Câu trước mốc: giả định hành vi chưa bị xử phạt theo quy định khác, cần người kiểm tra lại."
        cap.append((
            q("hieu_luc", ngay1, cau, f"Tại thời điểm này chưa bị xử phạt theo quy định tại {can_cu(uid)} "
              f"vì quy định này chỉ áp dụng từ {moc}.", [], None, gold1, cc1, ghi_chu=ghi, so_tien_khong_duoc_co=list(tk)),
            q("hieu_luc", ngay2, cau, f"Phạt tiền {fmt_khoang(*tk)}" + (" (mức áp dụng với cá nhân)." if ca_nhan else "."),
              list(tk), None, [uid], can_cu(uid), **({"nguon_sua_doi": nsd} if nsd else {})),
        ))

    # 3) Hành vi được NĐ 238/2026 bổ sung (trước mốc: chưa có quy định này)
    for uid, versions in kho.by.items():
        if not uid.startswith(ND):
            continue
        v = versions[0]
        if v["loai_phien_ban"] != "bo_sung" or v["cap"] not in ("Diem", "Khoan") or uid in da_viet:
            continue
        moc = v["hieu_luc_tu"]
        ngay2 = moc[:4] + "-10-01" if moc[5:] < "10-01" else moc
        ngay2 = max(ngay2, "2026-10-01") if moc < "2027" else str(int(moc[:4])) + "-03-01"
        ngay1 = "2026-06-01" if moc < "2027" else str(int(moc[:4]) - 1) + "-06-01"
        if v["cap"] == "Diem":
            tk = tien_khoan(v["parent_id"], ngay2)
            k = kho.ver(v["parent_id"], ngay2)
            chu = "Cá nhân" if k and "đối với cá nhân" in k["noi_dung"] else None
            beh = lam_sach(v["noi_dung"])
        else:
            m = RE_TIEN.match(v["noi_dung"])
            if not m or "một trong các hành vi" in v["noi_dung"]:
                continue
            tk = (tien(m.group(1)), tien(m.group(2)))
            rest = m.group(3)
            chu = None
            beh = lam_sach(re.sub(r"^(?:người điều khiển )", "người điều khiển ", rest))
        if not (tk and beh):
            continue
        h = bo_dong_tu(beh) if chu else beh
        cau = (f"{chu} {h} thì bị phạt bao nhiêu tiền?" if chu else f"{h[0].upper() + h[1:]} thì bị phạt bao nhiêu tiền?")
        cap.append((
            q("hieu_luc", ngay1, cau, f"Tại thời điểm này chưa có quy định xử phạt riêng đối với hành vi này; "
              f"quy định tại {can_cu(uid)} do {can_cu(v['nguon_sua_doi'])} bổ sung, có hiệu lực từ {ngay_vn(moc)}.",
              [], None, [uid], can_cu(uid), so_tien_khong_duoc_co=list(tk),
              ghi_chu="Câu trước mốc: giả định hành vi chưa bị xử phạt theo quy định khác, cần người kiểm tra lại."),
            q("hieu_luc", ngay2, cau, f"Phạt tiền {fmt_khoang(*tk)}" + (" (mức áp dụng với cá nhân)." if chu else "."),
              list(tk), None, [uid], can_cu(uid), nguon_sua_doi=[v["nguon_sua_doi"]]),
        ))

    # 4) Viết tay từ văn bản: chở trẻ em không dùng thiết bị an toàn (điểm m khoản 3 Điều 6 → khoản 1a Điều 6)
    cau = "Lái ô tô chở bé 6 tuổi, cao 1,1 m ngồi ghế sau nhưng không dùng ghế an toàn cho trẻ em thì bị xử phạt thế nào?"
    tk = tien_khoan("ND168_2024.D6.K3", "2026-03-01")
    if kho.ver("ND168_2024.D6.K1a", "2026-10-01") and tk:
        cap.append((
            q("hieu_luc", "2026-03-01", cau, f"Phạt tiền {fmt_khoang(*tk)} (hành vi không sử dụng thiết bị an toàn phù hợp "
              "cho trẻ em thuộc điểm m khoản 3 Điều 6 NĐ 168/2024).", list(tk), None,
              ["ND168_2024.D6.K3.m"], can_cu("ND168_2024.D6.K3.m")),
            q("hieu_luc", "2026-10-01", cau, "Phạt cảnh cáo (khoản 1a Điều 6 NĐ 168/2024, do NĐ 238/2026 bổ sung, "
              "hiệu lực từ 15/08/2026).", [], None, ["ND168_2024.D6.K1a"], can_cu("ND168_2024.D6.K1a"),
              nguon_sua_doi=["ND238_2026.D2.K1"], so_tien_khong_duoc_co=list(tk)),
        ))

    out = []
    for a, b in cap:
        out += [a, b]
    return out


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--so-cau", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/eval/bo_test_tu_dong.jsonl")
    ap.add_argument("--ghi-de", action="store_true",
                    help="cho phép ghi đè file đã có (MẤT các sửa đổi khi rà soát, xem docs/Huong_dan_ra_soat_bo_test.pdf)")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    kho = Kho()

    don, multi_tru = sinh_don_va_multi(kho, rng)
    toc_do = sinh_toc_do(kho)
    so_sanh = sinh_so_sanh(kho, rng)
    hieu_luc = sinh_hieu_luc(kho)
    print(f"Ứng viên: đơn {len(don)} · trừ điểm {len(multi_tru)} · tốc độ {len(toc_do)} · so sánh {len(so_sanh)} · "
          f"hiệu lực {len(hieu_luc)} ({len(hieu_luc) // 2} cặp)")

    N = args.so_cau
    n_hl = min(len(hieu_luc), round(N * 0.25) // 2 * 2)
    n_ss = min(len(so_sanh), round(N * 0.15))
    n_mh = min(len(multi_tru) + len(toc_do), round(N * 0.30))
    n_tdo = min(len(toc_do), n_mh // 2)
    n_don = N - n_hl - n_ss - n_mh

    def lay_deu(ds: list[dict], n: int) -> list[dict]:
        """Chọn n câu, chia đều theo Điều để không dồn vào Điều 6."""
        nhom = defaultdict(list)
        for x in ds:
            nhom[x.get("_dieu", 0)].append(x)
        for v in nhom.values():
            rng.shuffle(v)
        out, keys = [], sorted(nhom)
        while len(out) < n and any(nhom.values()):
            for k in keys:
                if nhom[k] and len(out) < n:
                    out.append(nhom[k].pop())
        return out

    chon = (lay_deu(don, n_don) + rng.sample(toc_do, n_tdo) + lay_deu(multi_tru, n_mh - n_tdo)
            + rng.sample(so_sanh, n_ss) + hieu_luc[:n_hl])
    # đánh số; câu hiệu lực theo cặp
    for i, x in enumerate(chon, 1):
        x["id"] = f"t{i:03d}"
        x.pop("_dieu", None)
    hl = [x for x in chon if x["loai"] == "hieu_luc"]
    for a, b in zip(hl[::2], hl[1::2]):
        a["cap_voi"], b["cap_voi"] = b["id"], a["id"]
    # Trường phục vụ rà soát: chia đều từng loại cho 3 thành viên; cặp hiệu lực giao cho cùng một người
    dem_loai: dict[str, int] = defaultdict(int)
    for x in chon:
        i = dem_loai[x["loai"]]
        dem_loai[x["loai"]] += 1
        nguoi = (i // 2 if x["loai"] == "hieu_luc" else i) % 3 + 1
        x.update({"trang_thai": "chua_duyet", "phan_cong": f"TV{nguoi}", "nguoi_duyet": ""})

    out = ROOT / args.out
    if out.exists() and not args.ghi_de:
        sys.exit(f"{args.out} đã có. Nếu nhóm đã rà soát file này, ghi đè sẽ mất các sửa đổi.\n"
                 f"Ghi ra file khác bằng --out, hoặc thêm --ghi-de nếu chắc chắn.")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for x in chon:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    dem = defaultdict(int)
    for x in chon:
        dem[x["loai"]] += 1
    print(f"Đã ghi {len(chon)} câu vào {args.out}: " + " · ".join(f"{k} {v}" for k, v in dem.items()))
    print(f"Kiểm tra: python scripts/check_questions.py {args.out}")


if __name__ == "__main__":
    main()
