"""Đọc file .docx thành danh sách khối theo đúng thứ tự trong văn bản.

Phụ trách: TV2.

Xử lý hai điểm mà đọc `document.paragraphs` thông thường bỏ sót:
1. Bảng nằm giữa các đoạn (vd. bảng tốc độ tối đa trong TT 38): đọc theo thứ tự thân văn bản,
   mỗi bảng thành một khối `kind="table"`, mỗi hàng một dòng, các ô nối bằng " | ".
2. Đánh số tự động của Word (vd. TT 38): ký hiệu "1." / "a)" không nằm trong chữ của đoạn.
   Hàm này tính lại ký hiệu từ numbering.xml và chèn vào đầu đoạn để parser dùng chung regex.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HAS_MARKER = re.compile(r"^(\d+[a-z]?\.|[a-zđ]\))\s")
_LETTERS = "abcdefghijklmnopqrstuvwxyz"


@dataclass
class Para:
    idx: int
    text: str
    bold: bool = False      # toàn bộ đoạn in đậm
    style: str = ""
    kind: str = "p"         # "p" (đoạn văn) hoặc "table"
    auto_num: bool = False  # ký hiệu đầu đoạn do Word tự đánh số, đã được chèn vào text


def _clean(s: str) -> str:
    return " ".join(s.split())


class _Numbering:
    """Tính ký hiệu đánh số tự động (chỉ hỗ trợ decimal "%1." và lowerLetter "%1)")."""

    def __init__(self, doc):
        from docx.oxml.ns import qn

        self.qn = qn
        self.num_abs: dict[str, str] = {}
        self.num_start_override: dict[tuple[str, str], int] = {}
        self.levels: dict[tuple[str, str], tuple[str, str, int]] = {}
        self.counters: dict[str, dict[str, int]] = {}
        self.seen_num: set[str] = set()
        try:
            root = doc.part.numbering_part.element
        except Exception:  # văn bản không có danh sách đánh số
            return
        for an in root.findall(qn("w:abstractNum")):
            aid = an.get(qn("w:abstractNumId"))
            for lv in an.findall(qn("w:lvl")):
                fmt, txt, st = (lv.find(qn(t)) for t in ("w:numFmt", "w:lvlText", "w:start"))
                self.levels[(aid, lv.get(qn("w:ilvl")))] = (
                    fmt.get(qn("w:val")) if fmt is not None else "",
                    txt.get(qn("w:val")) if txt is not None else "",
                    int(st.get(qn("w:val"))) if st is not None else 1,
                )
        for num in root.findall(qn("w:num")):
            nid = num.get(qn("w:numId"))
            self.num_abs[nid] = num.find(qn("w:abstractNumId")).get(qn("w:val"))
            for ov in num.findall(qn("w:lvlOverride")):
                so = ov.find(qn("w:startOverride"))
                if so is not None:
                    self.num_start_override[(nid, ov.get(qn("w:ilvl")))] = int(so.get(qn("w:val")))

    def marker(self, p) -> str | None:
        pPr = p._p.pPr
        numPr = pPr.numPr if pPr is not None else None
        if numPr is None or numPr.numId is None:
            return None
        nid = str(numPr.numId.val)
        ilvl = str(numPr.ilvl.val) if numPr.ilvl is not None else "0"
        aid = self.num_abs.get(nid)
        if aid is None or nid == "0":
            return None
        fmt, txt, start = self.levels.get((aid, ilvl), ("", "", 1))
        if fmt not in ("decimal", "lowerLetter"):
            return None
        cnt = self.counters.setdefault(aid, {})
        if nid not in self.seen_num:        # danh sách mới có startOverride -> bắt đầu lại
            self.seen_num.add(nid)
            if (nid, ilvl) in self.num_start_override:
                cnt[ilvl] = self.num_start_override[(nid, ilvl)] - 1
        cnt[ilvl] = cnt.get(ilvl, start - 1) + 1
        for deeper in [k for k in cnt if int(k) > int(ilvl)]:
            del cnt[deeper]                 # mục cấp trên tăng -> cấp dưới đếm lại
        n = cnt[ilvl]
        val = str(n) if fmt == "decimal" else _LETTERS[(n - 1) % 26]
        return txt.replace(f"%{int(ilvl) + 1}", val) if txt else None


def _table_text(table) -> str:
    rows = []
    for r in table.rows:
        cells: list[str] = []
        for c in r.cells:
            t = _clean(c.text)
            if t and (not cells or cells[-1] != t):   # ô gộp bị python-docx lặp lại
                cells.append(t)
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def read_docx(path: str | Path) -> list[Para]:
    import docx  # python-docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(path))
    numbering = _Numbering(d)
    out: list[Para] = []
    for i, el in enumerate(d.element.body.iterchildren()):
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "tbl":
            text = _table_text(Table(el, d))
            if text:
                out.append(Para(i, text, kind="table"))
        elif tag == "p":
            p = Paragraph(el, d)
            text = _clean(p.text)
            mk = numbering.marker(p)
            if not text:
                continue
            auto = False
            if mk and not _HAS_MARKER.match(text):
                text, auto = f"{mk} {text}", True
            runs = [r for r in p.runs if r.text.strip()]
            bold = bool(runs) and all(bool(r.bold) for r in runs)
            out.append(Para(i, text, bold, p.style.name if p.style is not None else "", "p", auto))
    return out
