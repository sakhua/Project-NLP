"""Đọc danh sách "điểm … khoản … Điều …" trong câu văn pháp luật thành các mã đích.

Dùng chung cho amendment_parser (đích của câu lệnh sửa đổi) và reference_extractor (dẫn chiếu).

Quy ước của văn bản pháp luật: số Điều/khoản đứng SAU và áp dụng cho các phần đứng trước nó:
  "điểm a khoản 2, điểm g khoản 5 Điều 6; điểm e khoản 1 Điều 7"
    → D6.K2.a, D6.K5.g, D7.K1.e
  "khoản 7 Điều 11, khoản 3 Điều 12, Điều 18, khoản 1, 3 và 6 Điều 25"
    → D11.K7, D12.K3, D18, D25.K1, D25.K3, D25.K6
Phần thiếu (không có Điều / khoản) được lấy từ ngữ cảnh truyền vào (Điều đang xét, "Điều này").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# "khoản 1, 3 và 6" → "khoản 1, khoản 3 và khoản 6";  "điểm d, đ" → "điểm d, điểm đ"
_RE_BARE = re.compile(
    r"\b(điểm|khoản|Điều)\s+(\w{1,4})((?:\s*(?:,|\bvà\b|\bhoặc\b)\s*(?!điểm\b|khoản\b|Điều\b)\w{1,4}\b(?!\s*\)))+)"
)
_RE_TOKEN = re.compile(r"\b(?P<kind>[Đđ]iểm|[Kk]hoản|Điều)\s+(?P<val>\d+[a-z]?\d?|[a-zđ]\d?|này)(?![\w/])")
_RE_QUOTED = re.compile(r"[“\"][^”\"]*[”\"]")


@dataclass(frozen=True)
class Ref:
    dieu: str | None          # '6', '25a', 'này' hoặc None
    khoan: str | None
    diem: str | None

    @property
    def level(self) -> str:
        return "Diem" if self.diem else "Khoan" if self.khoan else "Dieu" if self.dieu else "?"


_RE_DIEU_PAREN = re.compile(r"Điều\s+(\d+[a-z]?)\s*\(([^()]*?(?:điểm|khoản)[^()]*)\)")


def _expand_paren(text: str) -> str:
    """'Điều 13 (điểm a khoản 4; điểm a khoản 6)' → 'điểm a khoản 4 Điều 13; điểm a khoản 6 Điều 13'."""
    def repl(m: re.Match) -> str:
        return "; ".join(f"{seg.strip()} Điều {m.group(1)}" for seg in m.group(2).split(";") if seg.strip())
    return _RE_DIEU_PAREN.sub(repl, text)


def _expand_bare(text: str) -> str:
    text = _expand_paren(text)

    def repl(m: re.Match) -> str:
        kind = m.group(1)
        rest = re.sub(r"(,|\bvà\b|\bhoặc\b)\s*(\w{1,4})\b", lambda x: f"{x.group(1)} {kind} {x.group(2)}", m.group(3))
        return f"{kind} {m.group(2)}{rest}"
    return _RE_BARE.sub(repl, text)


def strip_quotes(text: str) -> str:
    """Bỏ các cụm trong ngoặc kép (cụm từ được thay, nội dung trích) trước khi đọc mã đích."""
    return _RE_QUOTED.sub(" ", text)


def parse_targets(text: str) -> list[Ref]:
    """Đọc mọi mã đích trong `text`, theo thứ tự xuất hiện. Không tra ngữ cảnh."""
    toks = [(m.group("kind").lower(), m.group("val")) for m in _RE_TOKEN.finditer(_expand_bare(text))]
    out: list[Ref] = []
    cur_dieu = cur_khoan = None
    dieu_used = khoan_used = True

    def flush_khoan():
        nonlocal khoan_used
        if cur_khoan is not None and not khoan_used:
            out.append(Ref(cur_dieu, cur_khoan, None))
            khoan_used = True

    def flush_dieu():
        nonlocal dieu_used
        if cur_dieu is not None and not dieu_used:
            out.append(Ref(cur_dieu, None, None))
            dieu_used = True

    for kind, val in reversed(toks):
        if kind == "điều":
            flush_khoan()
            flush_dieu()
            cur_dieu, dieu_used, cur_khoan = val, False, None
        elif kind == "khoản":
            flush_khoan()
            cur_khoan, khoan_used, dieu_used = val, False, True
        else:  # điểm
            out.append(Ref(cur_dieu, cur_khoan, val))
            khoan_used = dieu_used = True
            if cur_khoan is None:
                khoan_used = True
    flush_khoan()
    flush_dieu()
    out.reverse()
    return out


def resolve(ref: Ref, doc: str, dieu: str | None = None, khoan: str | None = None) -> str | None:
    """Ghép mã đầy đủ, điền phần thiếu từ ngữ cảnh. 'Điều này' = `dieu`. Trả None nếu thiếu Điều."""
    d = dieu if ref.dieu in (None, "này") else ref.dieu
    k = ref.khoan
    if k == "này":
        k = khoan
    if ref.diem and k is None:
        k = khoan
    if d is None:
        return None
    uid = f"{doc}.D{d}"
    if k:
        uid += f".K{k}"
    if ref.diem:
        if not k:
            return None
        uid += f".{ref.diem}"
    return uid
