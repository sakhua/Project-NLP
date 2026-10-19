"""Mã định danh chung cho PostgreSQL và Neo4j.

Quy ước: <MaVanBan>.D<số điều>[.K<số khoản>[.<điểm>]]
Ví dụ:   L36_2024.D10        ND168_2024.D6.K5      ND168_2024.D6.K5.a
Chương:  <MaVanBan>.C<số chương, chữ số Ả Rập>   ví dụ ND168_2024.C2
         (mã Điều không chứa Chương vì số Điều đã duy nhất trong một văn bản)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ID_RE = re.compile(
    r"^(?P<doc>[A-Z]+\d+_\d{4})"
    r"(?:\.C(?P<chuong>\d+)"
    r"|(?:\.D(?P<dieu>\d+[a-z]?))?(?:\.K(?P<khoan>\d+[a-z]?))?(?:\.(?P<diem>[a-zđ]))?)$"
)

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(s: str) -> int:
    """'IV' -> 4; chuỗi số thường thì đổi thẳng ('3' -> 3)."""
    s = s.strip().upper()
    if s.isdigit():
        return int(s)
    total, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAN[ch]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


@dataclass(frozen=True)
class UnitId:
    doc: str
    dieu: str | None = None
    khoan: str | None = None
    diem: str | None = None
    chuong: str | None = None

    def __str__(self) -> str:
        s = self.doc
        if self.chuong:
            return s + f".C{self.chuong}"
        if self.dieu:
            s += f".D{self.dieu}"
        if self.khoan:
            s += f".K{self.khoan}"
        if self.diem:
            s += f".{self.diem}"
        return s

    @property
    def level(self) -> str:
        if self.chuong:
            return "Chuong"
        if self.diem:
            return "Diem"
        if self.khoan:
            return "Khoan"
        if self.dieu:
            return "Dieu"
        return "VanBan"

    def parent(self) -> "UnitId | None":
        """Cha theo mã (Điều -> Văn bản). Cha thật của Điều có thể là Chương: xem parent_id trong corpus."""
        if self.diem:
            return UnitId(self.doc, self.dieu, self.khoan)
        if self.khoan:
            return UnitId(self.doc, self.dieu)
        if self.dieu or self.chuong:
            return UnitId(self.doc)
        return None


def make_id(doc: str, dieu: str | int | None = None, khoan: str | int | None = None,
            diem: str | None = None) -> str:
    if khoan is not None and dieu is None:
        raise ValueError("Có khoản thì phải có điều")
    if diem is not None and khoan is None:
        raise ValueError("Có điểm thì phải có khoản")
    return str(UnitId(doc, None if dieu is None else str(dieu),
                      None if khoan is None else str(khoan), diem))


def make_chuong_id(doc: str, so: str | int) -> str:
    """so: số La Mã ('II') hoặc số thường (2)."""
    return str(UnitId(doc, chuong=str(roman_to_int(str(so)))))


def parse_id(uid: str) -> UnitId:
    m = _ID_RE.match(uid)
    if not m:
        raise ValueError(f"Mã định danh không hợp lệ: {uid}")
    return UnitId(m["doc"], m["dieu"], m["khoan"], m["diem"], m["chuong"])
