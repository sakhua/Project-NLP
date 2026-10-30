"""Dựng các phiên bản hiệu lực của từng Điều/Khoản/Điểm (thiết kế: docs/thiet_ke_do_thi.md, cách A).

Phụ trách: TV1.   Gọi từ scripts/02_extract_relations.py, kết quả: data/processed/versions.jsonl

Đầu vào
  units       : corpus.jsonl (bản gốc của mọi văn bản, kể cả văn bản sửa đổi)
  amendments  : amendments.jsonl (mỗi dòng một thao tác nguyên tử, do amendment_parser tạo)
  manifest    : data/manifest.csv (hiệu lực của văn bản + "ngoại lệ: MÃ=YYYY-MM-DD; ...")
Đầu ra
  Mỗi phiên bản là một dòng của bảng don_vi:
  {vid, id, van_ban_id, cap, parent_id, so, thu_tu, tieu_de, noi_dung, ngu_canh, chuong, muc,
   co_trich_dan, hieu_luc_tu, hieu_luc_den, nguon_sua_doi, loai_phien_ban}

Quy tắc (đánh số theo tài liệu thiết kế)
  R1  Bản gốc có hiệu lực từ ngày hiệu lực của văn bản, trừ khi có ngoại lệ cho chính mã đó hoặc mã cha
      trong dòng manifest của văn bản đó.
  R2  Thao tác sửa đổi có hiệu lực từ ngày hiệu lực của văn bản sửa đổi, trừ khi dòng manifest của văn bản
      sửa đổi có ngoại lệ cho MÃ ĐÍCH (hoặc mã cha của mã đích).
  R3  Áp thao tác tại ngày d: phiên bản đang mở được đóng (hieu_luc_den = d), phiên bản mới mở từ d.
      hieu_luc_den là ngày KHÔNG còn hiệu lực (so sánh ngay < hieu_luc_den).
  R4  Bãi bỏ một đơn vị: đóng nó và mọi đơn vị con đang mở; không tạo phiên bản mới.
  R5  Nhiều thao tác cùng ngày trên cùng một mã: gộp vào một phiên bản, theo thứ tự trong văn bản.
  R6  Sửa cụm từ: thay chuỗi trong phiên bản đang mở; không tìm thấy cụm từ thì ghi cảnh báo, không đổi.
"""
from __future__ import annotations

import copy
import csv
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from graphrag.common.ids import make_vid, parse_id

RE_NGOAI_LE = re.compile(r"ngoại lệ:\s*(.+)$")
LOAI_THAO_TAC = {"SUA_DOI", "THAY_THE", "BO_SUNG", "BAI_BO"}
PHAM_VI = {"toan_bo", "cum_tu", "tieu_de"}


@dataclass
class DocInfo:
    hieu_luc_tu: date | None
    ngoai_le: dict[str, date] = field(default_factory=dict)


def load_manifest(path: str | Path) -> dict[str, DocInfo]:
    out: dict[str, DocInfo] = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            hl = date.fromisoformat(r["hieu_luc_tu"]) if r["hieu_luc_tu"].strip() else None
            ngoai_le = {}
            m = RE_NGOAI_LE.search(r.get("ghi_chu", ""))
            if m:
                for item in m.group(1).split(";"):
                    if "=" in item:
                        k, v = item.strip().split("=", 1)
                        ngoai_le[k.strip()] = date.fromisoformat(v.strip())
            out[r["id"]] = DocInfo(hl, ngoai_le)
    return out


def _ancestors(uid: str) -> list[str]:
    """Mã chính nó rồi lần lượt các mã cha: D6.K3.m -> [D6.K3.m, D6.K3, D6]."""
    out, p = [], parse_id(uid)
    while p is not None and p.level != "VanBan":
        out.append(str(p))
        p = p.parent()
    return out


def _ngay(info: DocInfo, uid: str) -> date | None:
    for a in _ancestors(uid):
        if a in info.ngoai_le:
            return info.ngoai_le[a]
    return info.hieu_luc_tu


def ngay_hieu_luc_goc(manifest: dict[str, DocInfo], unit: dict) -> date | None:
    """R1."""
    return _ngay(manifest[unit["van_ban_id"]], unit["id"])


def ngay_hieu_luc_thao_tac(manifest: dict[str, DocInfo], op: dict) -> date | None:
    """R2: op['nguon'] là mã đơn vị của văn bản sửa đổi, op['dich'] là mã bị sửa.
    Ngoại lệ trong dòng manifest của văn bản sửa đổi được tra theo mã đích (và mã cha của nó),
    rồi theo mã nguồn (vd. L118_2025.D7.K20.a=2026-01-01: riêng câu lệnh này có hiệu lực sớm hơn)."""
    if op.get("ngay_hieu_luc"):
        return date.fromisoformat(op["ngay_hieu_luc"])
    info = manifest[parse_id(op["nguon"]).doc]
    for a in _ancestors(op["dich"]) + _ancestors(op["nguon"]):
        if a in info.ngoai_le:
            return info.ngoai_le[a]
    return info.hieu_luc_tu


def _doc_label(units: list[dict]) -> dict[str, str]:
    """'ND168_2024' -> 'Nghị định 168/2024/NĐ-CP' (lấy từ ngu_canh của Điều đầu tiên)."""
    out = {}
    for u in units:
        if u["cap"] == "Dieu" and u["van_ban_id"] not in out:
            out[u["van_ban_id"]] = u["ngu_canh"].split(", Điều")[0]
    return out


class VersionBuilder:
    def __init__(self, units: list[dict], manifest: dict[str, DocInfo]):
        self.manifest = manifest
        self.labels = _doc_label(units)
        self.rows: list[dict] = []
        self.open: dict[str, dict] = {}      # mã đơn vị -> phiên bản đang mở (mới nhất)
        self.children: dict[str, list[str]] = {}
        self.warnings: list[str] = []
        for u in units:
            hl = ngay_hieu_luc_goc(manifest, u)
            if hl is None:
                self.warnings.append(f"{u['id']}: văn bản chưa có ngày hiệu lực, bỏ qua")
                continue
            row = {**u, "hieu_luc_tu": hl, "hieu_luc_den": None, "nguon_sua_doi": None, "loai_phien_ban": "goc"}
            self._add(row)

    # ---------- nội bộ ----------
    def _add(self, row: dict) -> None:
        row["vid"] = make_vid(row["id"], row["hieu_luc_tu"])
        self.rows.append(row)
        self.open[row["id"]] = row
        if row.get("parent_id"):
            self.children.setdefault(row["parent_id"], [])
            if row["id"] not in self.children[row["parent_id"]]:
                self.children[row["parent_id"]].append(row["id"])

    def _close(self, uid: str, d: date, recursive: bool, ngoai_le: dict[str, date] | None = None) -> None:
        """Đóng phiên bản đang mở. Khi đóng cả mục con, mục con có ngoại lệ riêng thì đóng theo ngày ngoại lệ
        (vd. TT105 bãi bỏ khoản 5 Điều 6 TT65 từ 01/07/2026 nhưng điểm a còn áp dụng đến hết 30/06/2027)."""
        cur = self.open.get(uid)
        if cur and cur["hieu_luc_den"] is None:
            if cur["hieu_luc_tu"] >= d:
                self.warnings.append(f"{uid}: bị đóng tại {d} nhưng phiên bản bắt đầu {cur['hieu_luc_tu']}")
                d_close = cur["hieu_luc_tu"]
            else:
                d_close = d
            cur["hieu_luc_den"] = d_close
        if recursive:
            for c in self.children.get(uid, []):
                self._close(c, (ngoai_le or {}).get(c, d), True, ngoai_le)

    def _last_thu_tu(self, uid: str) -> float | None:
        """thu_tu lớn nhất của uid và mọi mục con (để chèn mục mới SAU cả khối)."""
        r = self.open.get(uid)
        vals = [r["thu_tu"]] if r and r.get("thu_tu") is not None else []
        for c in self.children.get(uid, []):
            v = self._last_thu_tu(c)
            if v is not None:
                vals.append(v)
        return max(vals) if vals else None

    def _ctx(self, row: dict) -> str:
        """ngu_canh theo đúng định dạng của structure_parser, tính từ phiên bản đang mở của Điều / Khoản cha."""
        label = self.labels.get(row["van_ban_id"], row["van_ban_id"])
        if row["cap"] == "Chuong":
            return label
        p = parse_id(row["id"])
        dieu = row if row["cap"] == "Dieu" else self.open.get(f"{p.doc}.D{p.dieu}")
        ctx = label
        if dieu:
            ctx = f"{label}, Điều {dieu['so']}" + (f". {dieu['tieu_de']}" if dieu.get("tieu_de") else "")
        if row["cap"] == "Diem":
            k = self.open.get(row["parent_id"])
            if k:
                ctx += f" – khoản {k['so']}: {k['noi_dung'].split(chr(10))[0][:300]}"
        return ctx

    def _new_version(self, cur: dict, d: date, op: dict, loai: str) -> dict:
        """R3 + R5: cùng ngày, cùng nguồn sửa thì sửa tại chỗ; khác ngày thì đóng bản cũ, mở bản mới."""
        if cur["hieu_luc_tu"] == d:
            # cùng ngày: sửa ngay trên phiên bản đó (tránh hai phiên bản trùng vid)
            cur["nguon_sua_doi"] = op["nguon"]
            if cur["loai_phien_ban"] == "goc":
                cur["loai_phien_ban"] = loai
            return cur
        if d < cur["hieu_luc_tu"]:
            self.warnings.append(f"{op['nguon']}: sửa {cur['id']} từ {d} nhưng phiên bản hiện tại bắt đầu {cur['hieu_luc_tu']}")
        self._close(cur["id"], d, recursive=False)
        row = copy.deepcopy(cur)
        row.update(hieu_luc_tu=d, hieu_luc_den=None, nguon_sua_doi=op["nguon"], loai_phien_ban=loai)
        self._add(row)
        return row

    # ---------- thao tác ----------
    def apply(self, op: dict) -> None:
        loai, dich = op["loai"], op["dich"]
        if loai not in LOAI_THAO_TAC:
            self.warnings.append(f"{op['nguon']}: loại thao tác lạ '{loai}'")
            return
        d = ngay_hieu_luc_thao_tac(self.manifest, op)
        cur = self.open.get(dich)
        cur_open = cur is not None and cur["hieu_luc_den"] is None

        if loai == "BAI_BO":
            if not cur_open:
                self.warnings.append(f"{op['nguon']}: bãi bỏ {dich} nhưng không có phiên bản đang hiệu lực")
                return
            self._close(dich, d, recursive=True, ngoai_le=self.manifest[parse_id(op["nguon"]).doc].ngoai_le)
            return

        if loai == "BO_SUNG" and cur_open:
            self.warnings.append(f"{op['nguon']}: bổ sung {dich} nhưng mã đã tồn tại, xử lý như sửa đổi")
            loai = "SUA_DOI"

        if loai == "BO_SUNG":
            p = parse_id(dich)
            parent = op.get("parent_id") or str(p.parent())
            vt = op.get("vi_tri") or {}
            thu_tu = None
            if vt.get("sau") and self._last_thu_tu(vt["sau"]) is not None:
                thu_tu = self._last_thu_tu(vt["sau"]) + 0.001
            elif vt.get("truoc") and self.open.get(vt["truoc"]):
                thu_tu = self.open[vt["truoc"]]["thu_tu"] - 0.5
            pr = self.open.get(parent, {})
            row = {
                "id": dich, "van_ban_id": p.doc, "cap": p.level, "parent_id": parent,
                "so": p.diem or p.khoan or p.dieu, "thu_tu": thu_tu, "tieu_de": op.get("tieu_de"),
                "noi_dung": op["noi_dung_moi"], "ngu_canh": "",
                "chuong": pr.get("chuong"), "muc": pr.get("muc"), "co_trich_dan": False,
                "hieu_luc_tu": d, "hieu_luc_den": None, "nguon_sua_doi": op["nguon"], "loai_phien_ban": "bo_sung",
            }
            row["ngu_canh"] = self._ctx(row)
            self._add(row)
            return

        # SUA_DOI / THAY_THE
        if not cur_open:
            self.warnings.append(f"{op['nguon']}: sửa {dich} nhưng không có phiên bản đang hiệu lực")
            return
        pham_vi = op.get("pham_vi", "toan_bo")
        if pham_vi == "cum_tu":
            cu, moi = op["cum_tu_cu"], op.get("cum_tu_moi") or ""
            hay = cur["noi_dung"] + "\n" + (cur.get("tieu_de") or "")
            if cu not in hay and cu[:1].upper() + cu[1:] in hay:      # cụm từ đứng đầu câu: viết hoa chữ đầu
                cu, moi = cu[:1].upper() + cu[1:], (moi[:1].upper() + moi[1:]).lstrip(" ,")
            if cu not in hay:
                self.warnings.append(f"{op['nguon']}: không thấy cụm từ “{cu[:40]}” trong {dich}")
                return
            row = self._new_version(cur, d, op, loai.lower())
            clean = lambda t: re.sub(r" {2,}", " ", t.replace(cu, moi)).replace(" ,", ",").replace(" ;", ";")
            row["noi_dung"] = clean(row["noi_dung"])
            if row.get("tieu_de"):
                row["tieu_de"] = clean(row["tieu_de"])
        elif pham_vi == "tieu_de":
            row = self._new_version(cur, d, op, loai.lower())
            row["tieu_de"] = op["noi_dung_moi"]
        else:
            row = self._new_version(cur, d, op, loai.lower())
            row["noi_dung"] = op["noi_dung_moi"]
            if "tieu_de" in op:
                row["tieu_de"] = op["tieu_de"]
        row["ngu_canh"] = self._ctx(row)
        row["vid"] = make_vid(row["id"], row["hieu_luc_tu"])

    def result(self) -> list[dict]:
        out = []
        for r in self.rows:
            r = dict(r)
            r["hieu_luc_tu"] = r["hieu_luc_tu"].isoformat()
            r["hieu_luc_den"] = r["hieu_luc_den"].isoformat() if r["hieu_luc_den"] else None
            out.append(r)
        return out


def build_versions(units: list[dict], amendments: list[dict],
                   manifest: dict[str, DocInfo]) -> tuple[list[dict], list[str]]:
    """Trả về (các dòng của bảng don_vi, cảnh báo). Thao tác được áp theo ngày hiệu lực, rồi theo thứ tự trong file."""
    b = VersionBuilder(units, manifest)
    ordered = sorted(enumerate(amendments),
                     key=lambda x: (ngay_hieu_luc_thao_tac(manifest, x[1]) or date.max, x[0]))
    for _, op in ordered:
        b.apply(op)
    return b.result(), b.warnings


def valid_at(rows: list[dict], uid: str, ngay: date) -> dict | None:
    """Phiên bản của `uid` có hiệu lực tại `ngay` (giống điều kiện SQL trong postgres.SQL_VALID)."""
    s = ngay.isoformat()
    for r in rows:
        if r["id"] == uid and r["hieu_luc_tu"] <= s and (r["hieu_luc_den"] is None or s < r["hieu_luc_den"]):
            return r
    return None
