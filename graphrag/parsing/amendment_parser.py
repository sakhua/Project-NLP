"""Phân tích văn bản sửa đổi → các thao tác nguyên tử (data/processed/amendments.jsonl).

Phụ trách: TV1 (viết), TV2 (kiểm tra tay kết quả). Định dạng: docs/thiet_ke_do_thi.md, mục 5.
Kết quả được graphrag.parsing.versioning.build_versions dùng để dựng phiên bản hiệu lực.

Mỗi dòng là MỘT thao tác lên MỘT mã đích (mã của văn bản bị sửa):
  {"nguon": "ND238_2026.D2.K2", "dich": "ND168_2024.D6.K3.m",
   "loai": "SUA_DOI" | "THAY_THE" | "BO_SUNG" | "BAI_BO",
   "pham_vi": "toan_bo" | "cum_tu" | "tieu_de",
   "noi_dung_moi": "...", "tieu_de": "...", "cum_tu_cu": "...", "cum_tu_moi": "...",
   "vi_tri": {"sau": "..."} | {"truoc": "..."}, "parent_id": "..."}

Các dạng câu lệnh đã xử lý (khảo sát 6 văn bản sửa đổi trong corpus):
  "Sửa đổi, bổ sung điểm m khoản 3 như sau: “m) …”"            → SUA_DOI điểm
  "Sửa đổi, bổ sung khoản 2, khoản 3 Điều 17" (tiêu đề Điều) + nội dung → SUA_DOI từng khoản, điểm
  "Sửa đổi, bổ sung Điều 42" + toàn văn Điều                     → THAY_THE Điều + từng khoản/điểm,
                                                                      BAI_BO khoản/điểm cũ không còn
  "Bổ sung khoản 1a vào trước khoản 1 như sau: …"               → BO_SUNG (kèm vi_tri)
  "Sửa đổi, bổ sung khoản 18 và bổ sung khoản 18a vào sau khoản 18 Điều 9" → SUA_DOI + BO_SUNG
  "Sửa đổi, bổ sung tên Điều 7 như sau: “Điều 7. …”"           → SUA_DOI pham_vi tieu_de
  "Sửa đổi, bổ sung một số điểm của khoản 5 như sau:" (không có nội dung) → chỉ là ngữ cảnh cho các mục con
  "Thay thế cụm từ “A” bằng cụm từ “B” tại …", "Bỏ/Bãi bỏ cụm từ “A” tại …",
  "Bổ sung cụm từ “A” vào sau/trước cụm từ “B” tại …"          → SUA_DOI pham_vi cum_tu, mỗi mã đích một thao tác
  "Bãi bỏ khoản 3 Điều 6 và Điều 8."                             → BAI_BO
  Nội dung sửa đổi bị parser tách thành điểm con vì thiếu ngoặc kép (ND238_2026.D8.K3) → ghép lại làm nội dung.
Bỏ qua (ghi vào cảnh báo): phụ lục, biểu mẫu, "đoạn thứ …", văn bản ngoài kho (Luật Phí và lệ phí…).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .legal_refs import parse_targets, resolve, strip_quotes

RE_VERB = re.compile(r"^\s*(Sửa đổi,?\s*bổ sung|Sửa đổi|Bổ sung|Thay thế|Bãi bỏ|Bỏ)\b")
RE_NHU_SAU = re.compile(r"như sau\s*:")
RE_SO_HIEU = re.compile(r"(?:Luật|Nghị định|Thông tư)[^.;]{0,80}?số\s+(\d+/\d{4}/[A-ZĐ0-9\-]+)")
RE_C_DIEU = re.compile(r"^Điều\s+(\d+[a-z]?)\s*[\.:]\s*(.*)$")
RE_C_KHOAN = re.compile(r"^(\d+[a-z]?)\.\s+(.*)$")
RE_C_DIEM = re.compile(r"^([a-zđ]\d?)\)\s*(.*)$")
Q = "“\""
QC = "”\""


def _so_hieu_map() -> dict[str, str]:
    from .reference_extractor import SO_HIEU_TO_ID
    return SO_HIEU_TO_ID


def strip_outer_quotes(text: str) -> str:
    t = text.strip()
    if t[:1] in Q:
        t = t[1:]
    t = re.sub(r"[”\"]\s*[.;,]?\s*$", "", t)
    return t.strip()


@dataclass
class _Scope:
    doc: str
    dieu: str | None = None
    khoan: str | None = None


@dataclass
class _Item:
    cap: str
    dieu: str | None
    khoan: str | None = None
    diem: str | None = None
    text: str = ""
    tieu_de: str | None = None
    lines: list[str] = field(default_factory=list)

    def uid(self, doc: str) -> str:
        s = f"{doc}.D{self.dieu}"
        if self.khoan:
            s += f".K{self.khoan}"
        if self.diem:
            s += f".{self.diem}"
        return s


def parse_content(content: str, dieu: str | None, khoan: str | None) -> list[_Item]:
    """Tách khối trích dẫn thành Điều/Khoản/Điểm theo số thứ tự đầu dòng."""
    items: list[_Item] = []
    cur: _Item | None = None
    cur_khoan = None
    for line in [x.strip() for x in content.split("\n") if x.strip()]:
        if m := RE_C_DIEU.match(line):
            dieu, cur_khoan = m.group(1), None
            cur = _Item("Dieu", dieu, tieu_de=m.group(2).strip())
            items.append(cur)
        elif m := RE_C_KHOAN.match(line):
            cur_khoan = m.group(1)
            cur = _Item("Khoan", dieu, cur_khoan, lines=[m.group(2)])
            items.append(cur)
        elif m := RE_C_DIEM.match(line):
            cur = _Item("Diem", dieu, cur_khoan or khoan, m.group(1), lines=[m.group(2)])
            items.append(cur)
        elif cur is not None:
            cur.lines.append(line)
        else:
            cur = _Item("?", dieu, khoan, lines=[line])     # đoạn không đánh số ở đầu khối
            items.append(cur)
    for it in items:
        if it.cap == "Dieu":
            it.text = "\n".join(it.lines) if it.lines else f"Điều {it.dieu}. {it.tieu_de}"
        else:
            it.text = "\n".join(it.lines)
    return items


class AmendmentParser:
    """Đọc lần lượt các văn bản sửa đổi (theo ngày hiệu lực), nhớ mã nào đang tồn tại để biết SUA_DOI hay BO_SUNG."""

    def __init__(self, units: list[dict]):
        self.units = units
        self.parent: dict[str, str | None] = {u["id"]: u["parent_id"] for u in units}
        self.warnings: list[str] = []

    # ---------- tiện ích ----------
    def _exists(self, uid: str) -> bool:
        return uid in self.parent

    def _children(self, uid: str) -> list[str]:
        return [k for k, p in self.parent.items() if p == uid]

    def _remove(self, uid: str) -> None:
        for c in self._children(uid):
            self._remove(c)
        self.parent.pop(uid, None)

    def _doc_in(self, text: str, default: str) -> str | None:
        """Văn bản đích nhắc trong câu lệnh; None nếu nhắc văn bản ngoài kho."""
        found = [s.rstrip(".,;") for s in RE_SO_HIEU.findall(text)]
        if not found:
            return default
        mapped = [_so_hieu_map().get(s) for s in found]
        if any(m == default for m in mapped):
            return default
        known = [m for m in mapped if m]
        return known[0] if known else None

    @staticmethod
    def _split(u: dict) -> tuple[str | None, str]:
        """(câu lệnh, nội dung trích) của một đơn vị; câu lệnh None nếu không phải câu lệnh sửa đổi."""
        text = u["noi_dung"]
        first = text.split("\n")[0]
        if u["cap"] == "Dieu" and not RE_VERB.match(first):
            title = u.get("tieu_de") or ""
            if RE_VERB.match(title):
                return title, (text if u.get("co_trich_dan") else "")
            return None, ""
        if not RE_VERB.match(first):
            return None, ""
        m = RE_NHU_SAU.search(text)
        if m and not re.search(r"cụm từ", text[: m.start()]):
            return text[: m.end()], text[m.end():].strip()
        return text, ""

    def _scope_from(self, instr: str, scope: _Scope) -> _Scope:
        """Ngữ cảnh mới sau một câu lệnh (dùng cho các mục con và để điền phần thiếu của mã)."""
        # cả phần "vào sau …": "Bổ sung điểm c vào sau điểm b khoản 4" → khoản 4 áp cho cả điểm c
        refs = parse_targets(strip_quotes(instr))
        doc = self._doc_in(instr, scope.doc) or scope.doc
        dieu = next((r.dieu for r in reversed(refs) if r.dieu), None)
        khoan = next((r.khoan for r in reversed(refs) if r.khoan), None)
        if dieu:
            return _Scope(doc, dieu, khoan)
        return _Scope(doc, scope.dieu, khoan or scope.khoan)

    # ---------- phân tích một văn bản ----------
    def parse_doc(self, amending: str, target: str) -> list[dict]:
        doc_units = [u for u in self.units if u["van_ban_id"] == amending and u["cap"] != "Chuong"]
        kids: dict[str, list[dict]] = {}
        for u in doc_units:
            kids.setdefault(u["parent_id"], []).append(u)
        ops: list[dict] = []
        for u in doc_units:
            if u["cap"] == "Dieu":
                self._visit(u, _Scope(target), kids, ops)
        return ops

    def _visit(self, u: dict, scope: _Scope, kids: dict, ops: list[dict]) -> None:
        instr, content = self._split(u)
        if instr is None:
            return
        doc = self._doc_in(instr, scope.doc)
        if doc is None:
            self.warnings.append(f"{u['id']}: câu lệnh sửa văn bản ngoài kho, bỏ qua")
            return
        if re.search(r"Phụ lục|Mẫu số|biểu mẫu", instr) and not re.search(r"cụm từ", instr):
            self.warnings.append(f"{u['id']}: sửa phụ lục / biểu mẫu, bỏ qua")
            return
        if re.search(r"đoạn thứ|câu thứ", instr):
            self.warnings.append(f"{u['id']}: sửa một đoạn trong điều khoản, cần nhập tay: {instr[:80]}")
            return
        new_scope = self._scope_from(instr, _Scope(doc, scope.dieu, scope.khoan))
        children = kids.get(u["id"], [])

        if re.search(r"cụm từ\s*[“\"]|từ\s*[“\"]", instr):
            ops += self._phrase_ops(u["id"], instr, new_scope)
            return
        if RE_VERB.match(instr).group(1) in ("Bãi bỏ", "Bỏ") and not RE_NHU_SAU.search(instr):
            for r in parse_targets(strip_quotes(instr)):
                uid = resolve(r, new_scope.doc, scope.dieu, scope.khoan)
                if uid and self._exists(uid):
                    ops.append({"nguon": u["id"], "dich": uid, "loai": "BAI_BO"})
                    self._remove(uid)
                else:
                    self.warnings.append(f"{u['id']}: bãi bỏ {uid or r} nhưng không tìm thấy mã")
            return
        if not content.strip() and children and not any(self._split(c)[0] for c in children):
            # nội dung bị parser tách thành mục con vì thiếu ngoặc kép
            content = "\n".join((f"{c['so']}) " if c["cap"] == "Diem" else f"{c['so']}. ") + c["noi_dung"]
                                for c in children)
            children = []
        if content.strip():
            ops += self._content_ops(u["id"], instr, strip_outer_quotes(content), scope, new_scope)
        for c in children:
            self._visit(c, new_scope, kids, ops)

    # ---------- thao tác theo nội dung trích ----------
    def _content_ops(self, nguon: str, instr: str, content: str, scope: _Scope, ns: _Scope) -> list[dict]:
        ops: list[dict] = []
        doc = ns.doc
        items = parse_content(content, ns.dieu, ns.khoan)
        if any(it.cap == "?" for it in items):
            self.warnings.append(f"{nguon}: nội dung có đoạn không đánh số ở đầu, gộp vào thao tác đầu tiên")
            items = [it for it in items if it.cap != "?"] or items
        if not items or any(it.dieu is None for it in items):
            self.warnings.append(f"{nguon}: không xác định được Điều đích, bỏ qua")
            return ops

        if "tên Điều" in instr:
            it = items[0]
            ops.append({"nguon": nguon, "dich": f"{doc}.D{it.dieu}", "loai": "SUA_DOI", "pham_vi": "tieu_de",
                        "noi_dung_moi": it.tieu_de})
            return ops

        whole_dieu = not re.search(r"một số|tên Điều", instr)
        anchor = None
        m = re.search(r"vào (sau|trước)\s+(.+?)(?:\s+như sau|$)", strip_quotes(instr))
        if m:
            refs = parse_targets(m.group(2))
            if refs:
                anchor = (("sau" if m.group(1) == "sau" else "truoc"),
                          resolve(refs[0], doc, ns.dieu or scope.dieu, ns.khoan or scope.khoan))
        new_ids = {it.uid(doc) for it in items}
        prev_new: dict[str | None, str] = {}
        for it in items:
            uid = it.uid(doc)
            par = (f"{doc}.D{it.dieu}.K{it.khoan}" if it.cap == "Diem" else
                   f"{doc}.D{it.dieu}" if it.cap == "Khoan" else None)
            if self._exists(uid):
                loai = "THAY_THE" if it.cap == "Dieu" and whole_dieu else "SUA_DOI"
                op = {"nguon": nguon, "dich": uid, "loai": loai, "pham_vi": "toan_bo", "noi_dung_moi": it.text}
                if it.cap == "Dieu":
                    op["tieu_de"] = it.tieu_de
                ops.append(op)
                # thay cả khoản / cả Điều: mục con cũ không còn trong nội dung mới thì hết hiệu lực
                if it.cap == "Khoan" or (it.cap == "Dieu" and whole_dieu):
                    for c in self._children(uid):
                        if c not in new_ids:
                            ops.append({"nguon": nguon, "dich": c, "loai": "BAI_BO"})
                            self._remove(c)
            else:
                if it.cap == "Dieu":
                    par = self.parent.get(anchor[1]) if anchor and anchor[1] else doc
                if par != doc and par and not self._exists(par):
                    self.warnings.append(f"{nguon}: bổ sung {uid} nhưng không có đơn vị cha {par}")
                if par in prev_new:
                    vi_tri = {"sau": prev_new[par]}
                elif anchor and anchor[1] and self.parent.get(anchor[1]) == par:
                    vi_tri = {anchor[0]: anchor[1]}
                else:
                    sibs = [c for c in self._children(par)] if par else []
                    vi_tri = {"sau": sibs[-1]} if sibs else ({"sau": par} if par else {})
                op = {"nguon": nguon, "dich": uid, "loai": "BO_SUNG", "noi_dung_moi": it.text,
                      "parent_id": par, "vi_tri": vi_tri}
                if it.cap == "Dieu":
                    op["tieu_de"] = it.tieu_de
                ops.append(op)
                self.parent[uid] = par
                prev_new[par] = uid
        return ops

    # ---------- thao tác cụm từ ----------
    def _phrase_ops(self, nguon: str, instr: str, ns: _Scope) -> list[dict]:
        parts = re.split(r"(?<=[,;])\s*(?=cụm từ\s*[“\"])", instr)
        pending: list[tuple[str, str]] = []
        ops: list[dict] = []
        for part in parts:
            pairs: list[tuple[str, str]] = []
            for m in re.finditer(r"cụm từ\s*[“\"](.+?)[”\"]\s*bằng\s*cụm từ\s*[“\"](.+?)[”\"]", part):
                pairs.append((m.group(1), m.group(2)))
            for m in re.finditer(r"cụm từ\s*[“\"](.+?)[”\"]\s*(?:vào\s+)?(sau|trước)\s+(?:cụm\s+)?từ\s*[“\"](.+?)[”\"]",
                                 part):
                them, vt, moc = m.group(1), m.group(2), m.group(3)
                pairs.append((moc, moc + (" " if them[:1].isalnum() else "") + them if vt == "sau"
                              else them + (" " if them[-1:].isalnum() else "") + moc))
            if re.match(r"\s*(?:Bãi bỏ|Bỏ)\b", instr) and not pairs:
                pairs += [(m.group(1), "") for m in re.finditer(r"cụm từ\s*[“\"](.+?)[”\"]", part)]
            elif not pairs and re.match(r"\s*cụm từ", part) and re.match(r"\s*(?:Bãi bỏ|Bỏ)\b", instr):
                pairs += [(m.group(1), "") for m in re.finditer(r"cụm từ\s*[“\"](.+?)[”\"]", part)]
            pending += pairs
            tai = re.search(r"\btại\s+(.+)$", strip_quotes(part))
            if not tai:
                continue
            targets = [resolve(r, ns.doc, ns.dieu, ns.khoan) for r in parse_targets(tai.group(1))]
            for cu, moi in pending:
                for uid in targets:
                    if uid is None:
                        self.warnings.append(f"{nguon}: không đọc được mã đích trong “{tai.group(1)[:60]}”")
                        continue
                    ops.append({"nguon": nguon, "dich": uid, "loai": "SUA_DOI", "pham_vi": "cum_tu",
                                "cum_tu_cu": cu, "cum_tu_moi": moi})
            pending = []
        if pending:
            self.warnings.append(f"{nguon}: thay cụm từ nhưng không có “tại …”, cần nhập tay")
        return ops


def parse_amendments(units: list[dict], amending_doc_id: str, target_doc_id: str,
                     parser: AmendmentParser | None = None) -> list[dict]:
    """Thao tác của một văn bản sửa đổi. Truyền cùng `parser` cho nhiều văn bản để nhớ mã đã bổ sung/bãi bỏ."""
    p = parser or AmendmentParser(units)
    return p.parse_doc(amending_doc_id, target_doc_id)


def parse_all(units: list[dict], pairs: list[tuple[str, str]]) -> tuple[list[dict], list[str]]:
    """pairs: [(văn bản sửa đổi, văn bản bị sửa)] đã xếp theo ngày hiệu lực. Trả về (thao tác, cảnh báo)."""
    p = AmendmentParser(units)
    ops: list[dict] = []
    for a, t in pairs:
        ops += p.parse_doc(a, t)
    return ops, p.warnings
