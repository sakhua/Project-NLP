"""Nhận diện dẫn chiếu pháp lý trong nội dung điều khoản → cạnh THAM_CHIEU (data/processed/references.jsonl).

Phụ trách: TV1 (viết), TV2 (kiểm tra tay 50 dẫn chiếu ngẫu nhiên).
  {"src": "ND168_2024.D6.K16.b", "dst": "ND168_2024.D6.K9.b", "loai": "THAM_CHIEU",
   "text": "điểm b, điểm c, điểm d khoản 9 Điều này"}
Dẫn chiếu sang văn bản ngoài kho: "dst": null, "ngoai_pham_vi": true (giữ lại để thống kê, không nạp vào đồ thị).
Dẫn chiếu tới mã không có trong kho (lỗi đánh số hoặc lỗi parser): "khong_ton_tai": true.

Các dạng đã xử lý:
  "điểm a khoản 2 Điều 5", "khoản 3 Điều này", "điểm h khoản 5; khoản 6; điểm b, điểm c khoản 9 Điều này"
  "khoản 1, 3 và 6 Điều 25", "điểm a khoản này"
  "… Điều 6 của Nghị định này", "… Luật này"                        → cùng văn bản
  "… Nghị định số 151/2024/NĐ-CP", "… Luật Trật tự, an toàn giao thông đường bộ" → văn bản tương ứng trong kho
  "… Luật Xử lý vi phạm hành chính", "… Nghị định số 100/2019/NĐ-CP" → ngoài kho
"""
from __future__ import annotations

import re

from .legal_refs import _expand_bare, parse_targets, resolve

# Ánh xạ số hiệu → mã văn bản (đồng bộ với data/manifest.csv)
SO_HIEU_TO_ID = {
    "36/2024/QH15": "L36_2024",
    "118/2025/QH15": "L118_2025",
    "168/2024/NĐ-CP": "ND168_2024",
    "238/2026/NĐ-CP": "ND238_2026",
    "151/2024/NĐ-CP": "ND151_2024",
    "184/2025/NĐ-CP": "ND184_2025",
    "236/2026/NĐ-CP": "ND236_2026",
    "38/2024/TT-BGTVT": "TT38_2024",
    "65/2024/TT-BCA": "TT65_2024",
    "13/2025/TT-BCA": "TT13_2025",
    "105/2026/TT-BCA": "TT105_2026",
}
TEN_LUAT_TO_ID = {"Luật Trật tự, an toàn giao thông đường bộ": "L36_2024"}

_TOKEN = re.compile(r"\b(?:[Đđ]iểm|[Kk]hoản|Điều)\s+(?:\d+[a-z]?\d?|[a-zđ]\d?|này)(?![\w/])")
_GAP = re.compile(r"^[\s,;]*(?:(?:và|hoặc|tại|các)\s*)?[\s,;]*$")
_SAME_DOC = re.compile(r"^\s*(?:của\s+)?(?:Luật|Nghị định|Thông tư|Bộ luật)\s+này")
_SO_HIEU = re.compile(r"^\s*(?:của\s+)?(?:Luật|Nghị định|Thông tư|Bộ luật)[^,;.]{0,80}?số\s+(\d+/\d{4}/[A-ZĐ0-9\-]+)")
_TEN = re.compile(r"^\s*(?:của\s+)?((?:Bộ luật|Luật|Nghị định|Thông tư|Pháp lệnh|Quy chuẩn)\s+[A-ZĐ][^;.()]{0,80})")


def _doc_after(tail: str, fallback: str | None) -> str | None:
    """Văn bản được nhắc ngay sau cụm dẫn chiếu; không nhắc thì `fallback`; None = ngoài kho."""
    m = _SO_HIEU.match(tail)
    if m:
        return SO_HIEU_TO_ID.get(m.group(1).rstrip(".,;"))
    m = _TEN.match(tail)
    if m:
        for ten, doc in TEN_LUAT_TO_ID.items():
            if m.group(1).startswith(ten):
                return doc
        return None
    return fallback


_DIEU_SUA_VB_KHAC = re.compile(r", Điều \d+[a-z]?\. (?:Sửa đổi|Bãi bỏ|Bổ sung|Thay thế)")
_SO_HIEU_ANY = re.compile(r"(?:Luật|Nghị định|Thông tư)[^,;.]{0,80}?số\s+(\d+/\d{4}/[A-ZĐ0-9\-]+)")


def _doc_from_context(ngu_canh: str | None, current_doc: str) -> str | None:
    """Câu dẫn của Điều/khoản nói về văn bản khác ("… các điều, khoản sau của Luật Trật tự…",
    "Sửa đổi … Nghị định số 100/2019/NĐ-CP") thì dẫn chiếu không ghi tên văn bản thuộc văn bản đó."""
    if not ngu_canh:
        return current_doc
    for so in _SO_HIEU_ANY.findall(ngu_canh):
        doc = SO_HIEU_TO_ID.get(so.rstrip(".,;"))
        if doc != current_doc:
            return doc
    for ten, doc in TEN_LUAT_TO_ID.items():
        if ten in ngu_canh and doc != current_doc:
            return doc
    return current_doc


def find_references(text: str, current_id: str, known_ids: set[str] | None = None,
                    ngu_canh: str | None = None) -> list[dict]:
    """Tìm các dẫn chiếu trong `text` của đơn vị `current_id` (mã đơn vị, không phải vid).
    `ngu_canh`: đường dẫn của đơn vị (corpus), dùng để biết văn bản mặc định của dẫn chiếu; với Điều
    "Phạm vi điều chỉnh" nên truyền thêm câu dẫn của Điều ("… quy định chi tiết các điều, khoản sau của Luật …")."""
    from graphrag.common.ids import parse_id

    cur = parse_id(current_id)
    if ngu_canh and _DIEU_SUA_VB_KHAC.search(ngu_canh):
        return []       # Điều sửa đổi văn bản khác (vd. NĐ 168 Điều 52 sửa NĐ 100/2019): mọi mã trong đó thuộc văn bản kia
    default_doc = _doc_from_context(ngu_canh, cur.doc)
    text = _expand_bare(text)
    toks = list(_TOKEN.finditer(text))
    groups: list[tuple[int, int]] = []
    for t in toks:
        if groups and _GAP.match(text[groups[-1][1]:t.start()]):
            groups[-1] = (groups[-1][0], t.end())
        else:
            groups.append((t.start(), t.end()))
    out, seen = [], set()
    for a, b in groups:
        span = text[a:b]
        tail = text[b:b + 160]
        if "Điều này" in span or "khoản này" in span or _SAME_DOC.match(tail):
            doc = cur.doc
        else:
            doc = _doc_after(tail, default_doc)
        for r in parse_targets(span):
            if doc is None:
                out.append({"src": current_id, "dst": None, "loai": "THAM_CHIEU", "text": span, "ngoai_pham_vi": True})
                break
            dieu_ctx = cur.dieu if doc == cur.doc else None
            khoan_ctx = cur.khoan if doc == cur.doc and r.dieu in (None, "này") else None
            dst = resolve(r, doc, dieu_ctx, khoan_ctx)
            if not dst or dst == current_id or dst in seen:
                continue
            seen.add(dst)
            e = {"src": current_id, "dst": dst, "loai": "THAM_CHIEU", "text": span}
            if known_ids is not None and dst not in known_ids:
                e["khong_ton_tai"] = True
            out.append(e)
    return out
