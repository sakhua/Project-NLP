"""Tách văn bản thành Chương → (Mục) → Điều → Khoản → Điểm, xuất corpus.jsonl.

Phụ trách: TV2 (tuần 3). Dùng quy tắc (regex + máy trạng thái), không dùng LLM.

Mỗi dòng corpus.jsonl:
  {"id": "ND168_2024.D6.K5.a", "van_ban_id": "ND168_2024", "cap": "Diem",
   "parent_id": "ND168_2024.D6.K5", "so": "a", "thu_tu": 412, "tieu_de": null,
   "noi_dung": "...",              # chữ của RIÊNG đơn vị này, nguyên văn, không gồm đơn vị con
   "ngu_canh": "Nghị định 168/2024/NĐ-CP, Điều 6. ... – khoản 5: Phạt tiền từ ...",
   "chuong": "ND168_2024.C2", "muc": "Mục 1. ...", "co_trich_dan": false}

- `noi_dung` không chồng lấn giữa cha và con: Khoản chỉ chứa câu dẫn ("Phạt tiền từ ... sau đây:"),
  các điểm a), b) nằm ở đơn vị Điểm. Muốn xem toàn văn một Khoản thì ghép các con theo `thu_tu`.
- `ngu_canh` là "đường dẫn" (văn bản, Điều, câu dẫn của Khoản) để ghép trước `noi_dung` khi
  dựng BM25 / embedding: điểm "a) Không chấp hành hiệu lệnh của đèn tín hiệu" mới biết mức phạt.
- Ngày hiệu lực KHÔNG nằm trong corpus: được gán khi nạp DB từ manifest.csv và quan hệ sửa đổi.

Các trường hợp đặc biệt đã xử lý (xem khảo sát dữ liệu):
- Văn bản sửa đổi trích nguyên văn điều khoản mới trong ngoặc kép (“...” hoặc "...") → phần trích
  được gắn vào đơn vị đang chứa câu lệnh sửa đổi, KHÔNG tách thành Điều/Khoản của văn bản sửa đổi
  (co_trich_dan = true). Bước 2 (amendment_parser) sẽ dùng phần này.
- Phạm vi: văn bản sửa nhiều luật/nghị định (L118, ND184, TT13) chỉ giữ các Điều trong `scope`.
- Dừng ở bảng chữ ký / "Nơi nhận" / "PHỤ LỤC" (biểu mẫu, phụ lục không đưa vào v1).
- Bảng trong thân Điều (TT 38) và đánh số tự động của Word: xử lý trong docx_reader.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from graphrag.common.ids import make_chuong_id, make_id

from .docx_reader import Para, read_docx

RE_CHUONG = re.compile(r"^Chương\s+([IVXLC]+|\d+)\b\.?\s*(.*)$", re.IGNORECASE)
RE_MUC = re.compile(r"^Mục\s+(\d+)\b\.?\s*(.*)$")
RE_DIEU = re.compile(r"^Điều\s+(\d+[a-z]?)\s*[\.:]\s*(.*)$")
RE_KHOAN = re.compile(r"^(\d+[a-z]?)\.\s+(.*)$")
RE_DIEM = re.compile(r"^([a-zđ])\)\s+(.*)$")
RE_INLINE_QUOTE = re.compile(r"như sau:?\s*[“\"]")   # "Sửa đổi ... như sau: “Điều 7. ...”"
RE_STOP = re.compile(r"^(Nơi nhận|PHỤ LỤC\b)")
RE_SIGNATURE = re.compile(r"Nơi nhận|TM\. CHÍNH PHỦ|CHỦ TỊCH QUỐC HỘI|\bBỘ TRƯỞNG\b|THỦ TƯỚNG")
VIET_DIEM = "abcdđeghiklmnopqrstuvxy"   # thứ tự điểm trong văn bản pháp luật Việt Nam


@dataclass
class ParseResult:
    units: list[dict]
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


class _Parser:
    def __init__(self, doc_id: str, scope: set[str] | None, label: str):
        self.doc, self.scope, self.label = doc_id, scope, label
        self.units: dict[str, dict] = {}
        self.order: list[str] = []
        self.warn: list[str] = []
        self.started = False
        self.stopped_at: str | None = None
        self.chuong = self.muc = None
        self.pending_title: dict | str | None = None
        self.dieu = self.khoan = self.diem = None
        self.dieu_in_scope = False
        self.last_dieu_num = 0
        self.in_quote, self.quote_kind, self.quote_balance, self.quote_len = False, "", 0, 0
        self.n_quote_blocks = self.n_tables = self.n_auto = 0

    # ---------- tạo đơn vị ----------
    def _new(self, uid: str, cap: str, parent: str, so: str | None, tieu_de: str | None, text: str) -> dict:
        if uid in self.units:
            self.warn.append(f"Trùng mã {uid}: gộp nội dung vào đơn vị đã có")
            u = self.units[uid]
            if text:
                u["parts"].append(text)
            return u
        u = {"id": uid, "van_ban_id": self.doc, "cap": cap, "parent_id": parent, "so": so,
             "thu_tu": len(self.order) + 1, "tieu_de": tieu_de, "parts": [text] if text else [],
             "chuong": self.chuong["id"] if self.chuong else None, "muc": self.muc,
             "co_trich_dan": False}
        if cap == "Chuong":
            u["chuong"] = uid
        self.units[uid] = u
        self.order.append(uid)
        return u

    def _target(self) -> dict | None:
        if not self.dieu_in_scope:
            return None
        return self.diem or self.khoan or self.dieu

    def _append(self, text: str, quoted: bool = False) -> None:
        t = self._target()
        if t is not None:
            t["parts"].append(text)
            if quoted:
                t["co_trich_dan"] = True

    # ---------- ngoặc kép (nội dung trích của văn bản sửa đổi) ----------
    def _quote_closed(self, text: str, opening: bool) -> bool:
        if self.quote_kind == "curly":
            self.quote_balance += text.count("“") - text.count("”")
            return self.quote_balance <= 0
        tail = text.rstrip(" .;,:")
        return tail.endswith('"') and (not opening or text.count('"') >= 2)

    def _enter_quote(self, text: str) -> None:
        self.in_quote, self.quote_len = True, 0
        self.quote_kind = "curly" if text.startswith("“") else "straight"
        self.quote_balance = 0
        self.n_quote_blocks += 1
        self._append(text, quoted=True)
        if self._quote_closed(text, opening=True):
            self.in_quote = False

    # ---------- xử lý từng khối ----------
    def feed(self, p: Para) -> bool:
        """Trả về False khi gặp điểm dừng (chữ ký, nơi nhận, phụ lục)."""
        t = p.text
        if p.kind == "table":
            if self.started and not self.in_quote and RE_SIGNATURE.search(t):
                self.stopped_at = "bảng chữ ký / nơi nhận"
                return False
            if self.started:
                self.n_tables += 1
                self._append(t, quoted=self.in_quote)
            return True
        self.n_auto += p.auto_num

        if self.in_quote:
            m = RE_DIEU.match(t)
            if m and not t.startswith(("“", '"')) and self._num(m.group(1)) == self.last_dieu_num + 1 \
                    and self.quote_len > 0:
                self.warn.append(f"Ngoặc kép không đóng trước 'Điều {m.group(1)}': tự đóng")
                self.in_quote = False          # rơi xuống xử lý như đoạn thường
            else:
                self.quote_len += 1
                self._append(t, quoted=True)
                if self._quote_closed(t, opening=False):
                    self.in_quote = False
                return True

        if self.started and RE_STOP.match(t):
            self.stopped_at = t[:20]
            return False
        if self.started and t.startswith(("“", '"')):
            self._enter_quote(t)
            return True

        m = RE_CHUONG.match(t)
        if m and len(t) < 200:
            self.started = True
            self.chuong = self._new(make_chuong_id(self.doc, m.group(1)), "Chuong", self.doc,
                                    m.group(1).upper(), m.group(2) or None, "")
            self.muc, self.dieu, self.khoan, self.diem = None, None, None, None
            self.dieu_in_scope = False
            self.pending_title = None if m.group(2) else self.chuong
            return True
        m = RE_MUC.match(t)
        if m and self.started and len(t) < 200:
            self.muc = f"Mục {m.group(1)}" + (f". {m.group(2)}" if m.group(2) else "")
            self.pending_title = None if m.group(2) else "muc"
            self.dieu = self.khoan = self.diem = None
            return True
        m = RE_DIEU.match(t)
        if m:
            self.started = True
            self.pending_title = None
            so = m.group(1)
            self.last_dieu_num = self._num(so)
            self.dieu_in_scope = self.scope is None or so in self.scope
            self.khoan = self.diem = None
            self.dieu = None
            if self.dieu_in_scope:
                parent = self.chuong["id"] if self.chuong else self.doc
                self.dieu = self._new(make_id(self.doc, so), "Dieu", parent, so, m.group(2).strip() or None, "")
            return True

        if self.pending_title is not None:          # dòng tên Chương / Mục ngay sau số hiệu
            if self.pending_title == "muc":
                self.muc += f". {t}"
                self.pending_title = None
            else:
                ch = self.pending_title
                if ch["tieu_de"] is None:
                    ch["tieu_de"] = t
                elif t.isupper():
                    ch["tieu_de"] += " " + t
                else:
                    self.pending_title = None
                    return self.feed(p)
                if not t.isupper():
                    self.pending_title = None
            return True
        if not self.started:
            return True                              # phần đầu: quốc hiệu, tên, căn cứ

        m = RE_KHOAN.match(t)
        if m and self.dieu is not None:
            so = m.group(1)
            prev = self.dieu.get("_last_khoan")
            if prev is not None and so.isdigit() and prev.isdigit() and int(so) != int(prev) + 1:
                self.warn.append(f"{self.dieu['id']}: khoản {prev} → {so} không liên tiếp")
            self.dieu["_last_khoan"] = so
            self.khoan = self._new(make_id(self.doc, self.dieu["so"], so), "Khoan", self.dieu["id"], so, None,
                                   m.group(2))
            self.khoan["co_trich_dan"] |= bool(RE_INLINE_QUOTE.search(t))
            self.diem = None
            return True
        m = RE_DIEM.match(t)
        if m and self.dieu is not None:
            so = m.group(1)
            if self.khoan is None:
                self.warn.append(f"{self.dieu['id']}: điểm {so}) không thuộc khoản nào → gộp vào Điều")
                self._append(t)
                return True
            prev = self.khoan.get("_last_diem")
            exp = VIET_DIEM[VIET_DIEM.index(prev) + 1] if prev and prev in VIET_DIEM[:-1] else "a"
            so_goc = so
            if make_id(self.doc, self.dieu["so"], self.khoan["so"], so) in self.units:
                # Ký hiệu điểm bị lặp trong văn bản gốc (lỗi đánh máy): đặt theo thứ tự để mã không trùng
                so = exp
                self.warn.append(f"{self.khoan['id']}: điểm '{so_goc}' bị lặp → đặt lại thành '{so}' "
                                 f"(đối chiếu văn bản gốc trên vbpl.vn)")
            elif so != exp:
                self.warn.append(f"{self.khoan['id']}: điểm sau '{prev or '-'}' là '{so}' (dự kiến '{exp}')")
            self.khoan["_last_diem"] = so
            self.diem = self._new(make_id(self.doc, self.dieu["so"], self.khoan["so"], so), "Diem",
                                  self.khoan["id"], so, None, m.group(2))
            self.diem["co_trich_dan"] |= bool(RE_INLINE_QUOTE.search(t))
            if so != so_goc:
                self.diem["so_goc"] = so_goc
            return True
        self._append(t, quoted=bool(RE_INLINE_QUOTE.search(t)))   # dòng nối tiếp, gạch đầu dòng "-", "+"
        return True

    @staticmethod
    def _num(so: str) -> int:
        return int(re.match(r"\d+", so).group())

    # ---------- hoàn thiện ----------
    def finish(self) -> ParseResult:
        if self.in_quote:
            self.warn.append("Kết thúc văn bản khi ngoặc kép chưa đóng")
        out: list[dict] = []
        for uid in self.order:
            u = self.units[uid]
            noi_dung = "\n".join(u.pop("parts")).strip()
            u.pop("_last_khoan", None)
            u.pop("_last_diem", None)
            if not noi_dung:
                noi_dung = (f"Điều {u['so']}. {u['tieu_de']}" if u["cap"] == "Dieu"
                            else u["tieu_de"] or f"Chương {u['so']}")
            u["noi_dung"] = noi_dung
            out.append(u)
        by_id = {u["id"]: u for u in out}
        for u in out:
            u["ngu_canh"] = self._context(u, by_id)
        stats = {"Chuong": 0, "Dieu": 0, "Khoan": 0, "Diem": 0}
        for u in out:
            stats[u["cap"]] += 1
        stats.update(khoi_trich_dan=self.n_quote_blocks, bang=self.n_tables, danh_so_tu_dong=self.n_auto,
                     dung_tai=self.stopped_at)
        return ParseResult(out, self.warn, stats)

    def _context(self, u: dict, by_id: dict) -> str:
        if u["cap"] == "Chuong":
            return self.label
        dieu_id = make_id(self.doc, u["id"].split(".D")[1].split(".")[0])
        d = by_id.get(dieu_id)
        ctx = f"{self.label}, Điều {d['so']}" + (f". {d['tieu_de']}" if d and d["tieu_de"] else "") if d else self.label
        if u["cap"] == "Diem":
            k = by_id.get(u["parent_id"])
            if k:
                lead = k["noi_dung"].split("\n")[0]
                ctx += f" – khoản {k['so']}: {lead[:300]}"
        return ctx


def parse(doc_id: str, docx_path: str | Path, scope: set[str] | None = None, label: str | None = None) -> ParseResult:
    p = _Parser(doc_id, scope, label or doc_id)
    for para in read_docx(docx_path):
        if not p.feed(para):
            break
    return p.finish()


def parse_document(doc_id: str, docx_path: str | Path, scope: set[str] | None = None,
                   label: str | None = None) -> list[dict]:
    """Trả về danh sách đơn vị văn bản theo định dạng corpus.jsonl."""
    return parse(doc_id, docx_path, scope, label).units


def parse_scope(pham_vi: str | None) -> set[str] | None:
    """Cột pham_vi trong manifest: 'toan_bo' (hoặc trống) = mọi Điều; 'dieu:7,11' = chỉ Điều 7 và 11."""
    if not pham_vi or pham_vi.strip() in ("toan_bo", ""):
        return None
    if pham_vi.startswith("dieu:"):
        return {s.strip() for s in pham_vi[5:].split(",") if s.strip()}
    raise ValueError(f"pham_vi không hợp lệ: {pham_vi!r} (dùng 'toan_bo' hoặc 'dieu:7,11')")


def write_corpus(units: list[dict], out_path: str | Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        for u in units:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
