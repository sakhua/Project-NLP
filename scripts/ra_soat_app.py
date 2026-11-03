"""Giao diện rà soát bộ câu hỏi golden (hướng dẫn: docs/Huong_dan_ra_soat_bo_test.pdf).

Chạy:  streamlit run scripts/ra_soat_app.py          (cần pip install -e ".[demo]")
       streamlit run scripts/ra_soat_app.py -- --file data/eval/questions_TV1.jsonl

- Lọc câu theo người được giao, loại, trạng thái, từ khóa; chuyển câu bằng nút Trước / Sau.
- Bên phải hiện nội dung các điều khoản gold đúng phiên bản theo ngày áp dụng, kèm kiểm tra tự động.
- Bấm Lưu: chỉ dòng của câu đang sửa được ghi lại vào file JSONL (đọc lại file ngay trước khi ghi, nên không
  đè lên câu người khác vừa lưu). Lần lưu đầu mỗi phiên tạo bản sao lưu trong data/eval/sao_luu/.
Không cần Docker hay API key: chỉ đọc data/processed/versions.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--file", default="data/eval/bo_test_tu_dong.jsonl")
ARGS, _ = ap.parse_known_args()
FILE = (ROOT / ARGS.file).resolve()

TRANG_THAI = {"chua_duyet": "Chưa duyệt", "dat": "Đạt", "da_sua": "Đã sửa", "loai": "Loại"}
TEN_LOAI = {"don": "Đơn", "multi_hop": "Multi-hop", "hieu_luc": "Hiệu lực", "so_sanh": "So sánh"}
RE_TIEN_VB = re.compile(r"\d{1,3}(?:\.\d{3})+")

st.set_page_config(page_title="Rà soát bộ câu hỏi", layout="wide")


# ---------------------------------------------------------------- dữ liệu

@st.cache_resource(show_spinner="Đang đọc versions.jsonl…")
def kho() -> tuple[dict, dict]:
    by, con = defaultdict(list), defaultdict(list)
    for line in open(ROOT / "data/processed/versions.jsonl", encoding="utf-8"):
        v = json.loads(line)
        if not by[v["id"]]:
            con[v["parent_id"]].append(v["id"])
        by[v["id"]].append(v)
    return dict(by), dict(con)


def phien_ban(uid: str, ngay: str) -> dict | None:
    for v in kho()[0].get(uid, []):
        if v["hieu_luc_tu"] <= ngay and (v["hieu_luc_den"] is None or ngay < v["hieu_luc_den"]):
            return v
    return None


def doc_file() -> list[dict]:
    return [json.loads(line) for line in open(FILE, encoding="utf-8-sig") if line.strip()]


def luu_cau(q: dict) -> None:
    """Đọc lại file, thay đúng dòng có cùng id, ghi ra file tạm rồi đổi tên (không làm hỏng file nếu lỗi giữa chừng)."""
    if not st.session_state.get("da_sao_luu"):
        bk = ROOT / "data/eval/sao_luu" / f"{FILE.stem}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
        bk.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FILE, bk)
        st.session_state.da_sao_luu = str(bk.relative_to(ROOT))
    qs = doc_file()
    idx = next(i for i, x in enumerate(qs) if x["id"] == q["id"])
    qs[idx] = q
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in qs), encoding="utf-8")
    os.replace(tmp, FILE)


def so_nguyen(s: str) -> list[int]:
    """'18.000.000, 20000000' → [18000000, 20000000]."""
    out = []
    for p in re.split(r"[,;\s]+", s.strip()):
        if p:
            p = p.replace(".", "").replace("_", "")
            if not p.isdigit():
                raise ValueError(f"'{p}' không phải số tiền")
            out.append(int(p))
    return out


def ds_ma(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,;\s]+", s) if x.strip()]


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# ---------------------------------------------------------------- kiểm tra một câu

def kiem_tra(q: dict, tat_ca: dict[str, dict]) -> tuple[list[str], list[str]]:
    loi, cb = [], []
    by = kho()[0]
    gold, nsd = q.get("gold_ids") or [], q.get("nguon_sua_doi") or []
    if not gold:
        loi.append("gold_ids rỗng")
    text = ""
    for g in gold + nsd:
        if g not in by:
            (cb if nsd and g in gold else loi).append(f"Mã {g} không có trong dữ liệu")
            continue
        v = phien_ban(g, q["ngay_ap_dung"]) or by[g][-1]
        if g in gold and not phien_ban(g, q["ngay_ap_dung"]) and q.get("so_tien"):
            cb.append(f"{g} không có hiệu lực vào {q['ngay_ap_dung']}")
        text += " " + (v.get("ngu_canh") or "") + " " + v["noi_dung"]
        cha = phien_ban(v["parent_id"], q["ngay_ap_dung"])
        if cha:
            text += " " + cha["noi_dung"]
        text += " ".join(x["noi_dung"] for x in by[g])
    so = {int(x.replace(".", "")) for x in RE_TIEN_VB.findall(text)}
    for t in q.get("so_tien", []):
        if t not in so:
            cb.append(f"Số tiền {fmt(t)} không thấy trong nội dung các gold (kể cả câu dẫn của khoản)")
    if q.get("diem_tru") and not re.search(rf"\b0?{q['diem_tru']} điểm", text):
        cb.append(f"'{q['diem_tru']} điểm' không thấy trong nội dung các gold")
    if re.search(r"\b(Điều|khoản|điểm)\s+\d", q.get("cau_hoi", ""), re.I):
        cb.append("Câu hỏi nhắc số điều/khoản/điểm")
    if q.get("cap_voi"):
        cap = tat_ca.get(q["cap_voi"])
        if cap and cap["cau_hoi"] != q["cau_hoi"]:
            cb.append(f"Câu cặp {q['cap_voi']} có câu hỏi khác câu này: sửa cả hai cho giống nhau")
        if cap and cap.get("dap_an") == q.get("dap_an"):
            cb.append(f"Đáp án trùng với câu cặp {q['cap_voi']}")
    return loi, cb


# ---------------------------------------------------------------- giao diện

if not FILE.exists():
    st.error(f"Không thấy file {FILE}")
    st.stop()
qs = doc_file()
tat_ca = {q["id"]: q for q in qs}

with st.sidebar:
    st.header("Rà soát bộ câu hỏi")
    st.caption(str(FILE.relative_to(ROOT)) if FILE.is_relative_to(ROOT) else str(FILE))
    nguoi = st.selectbox("Bạn là", ["TV1", "TV2", "TV3"], key="nguoi")
    pc = st.selectbox("Câu được giao cho", ["Tất cả", "TV1", "TV2", "TV3"], index=["TV1", "TV2", "TV3"].index(nguoi) + 1)
    loai = st.multiselect("Loại câu", list(TEN_LOAI), format_func=TEN_LOAI.get)
    tt = st.multiselect("Trạng thái", list(TRANG_THAI), format_func=TRANG_THAI.get)
    chi_can_xem = st.checkbox("Chỉ câu có dấu RÀ SOÁT / giả định")
    tim = st.text_input("Tìm trong câu hỏi, đáp án, mã")

    def hop(q: dict) -> bool:
        if pc != "Tất cả" and q.get("phan_cong") != pc:
            return False
        if loai and q["loai"] not in loai:
            return False
        if tt and q.get("trang_thai", "chua_duyet") not in tt:
            return False
        if chi_can_xem and not re.search(r"RÀ SOÁT|giả định", q.get("ghi_chu", ""), re.I):
            return False
        return not tim or tim.lower() in json.dumps(q, ensure_ascii=False).lower()

    loc = [q for q in qs if hop(q)]
    mine = [q for q in qs if pc == "Tất cả" or q.get("phan_cong") == pc]
    xong = sum(q.get("trang_thai", "chua_duyet") != "chua_duyet" for q in mine)
    st.progress(xong / len(mine) if mine else 0.0, text=f"Đã rà {xong}/{len(mine)} câu")
    dem = defaultdict(int)
    for q in mine:
        dem[q.get("trang_thai", "chua_duyet")] += 1
    st.caption(" · ".join(f"{TRANG_THAI[k]} {dem[k]}" for k in TRANG_THAI))
    if st.session_state.get("da_sao_luu"):
        st.caption(f"Bản sao lưu: {st.session_state.da_sao_luu}")

if not loc:
    st.info("Không có câu nào khớp bộ lọc.")
    st.stop()

ids = [q["id"] for q in loc]
if st.session_state.get("chuyen_toi") in ids:      # đặt từ lần chạy trước (nút Lưu và sang câu sau)
    st.session_state.chon = st.session_state.pop("chuyen_toi")
if st.session_state.get("chon") not in ids:
    st.session_state.chon = ids[0]
c1, c2, c3 = st.columns([1, 6, 1])
i = ids.index(st.session_state.chon)
if c1.button("◀ Trước", use_container_width=True, disabled=i == 0):
    st.session_state.chon = ids[i - 1]
    st.rerun()
if c3.button("Sau ▶", use_container_width=True, disabled=i == len(ids) - 1):
    st.session_state.chon = ids[i + 1]
    st.rerun()
c2.selectbox("Câu", ids, key="chon", label_visibility="collapsed",
             format_func=lambda x: f"{x} · {TEN_LOAI[tat_ca[x]['loai']]} · "
                                   f"{TRANG_THAI.get(tat_ca[x].get('trang_thai', 'chua_duyet'))} · {tat_ca[x]['cau_hoi'][:90]}")

q = tat_ca[st.session_state.chon]
qid = q["id"]
trai, phai = st.columns([1.1, 1])

with trai:
    st.subheader(f"{qid} · {TEN_LOAI[q['loai']]} · ngày {q['ngay_ap_dung']}")
    st.caption(f"Giao cho {q.get('phan_cong', '–')} · người duyệt: {q.get('nguoi_duyet') or '–'}"
               + (f" · cặp với {q['cap_voi']} (ngày {tat_ca[q['cap_voi']]['ngay_ap_dung']})" if q.get("cap_voi") in tat_ca else ""))
    if q.get("ghi_chu") and re.search(r"RÀ SOÁT|giả định", q["ghi_chu"], re.I):
        st.warning(q["ghi_chu"])
    with st.form(f"f_{qid}"):
        cau_hoi = st.text_area("Câu hỏi", q["cau_hoi"], height=90)
        dap_an = st.text_area("Đáp án", q["dap_an"], height=90)
        a, b = st.columns(2)
        so_tien = a.text_input("Số tiền (đồng, cách nhau dấu phẩy)", ", ".join(fmt(x) for x in q.get("so_tien", [])))
        diem = b.text_input("Điểm trừ (để trống nếu không trừ)", "" if q.get("diem_tru") is None else str(q["diem_tru"]))
        gold = st.text_area("gold_ids (mỗi mã một dòng)", "\n".join(q.get("gold_ids", [])), height=80)
        nsd = st.text_input("nguon_sua_doi (mã văn bản sửa đổi, nếu có)", ", ".join(q.get("nguon_sua_doi") or []))
        can_cu = st.text_input("Căn cứ", q.get("can_cu", ""))
        ghi_chu = st.text_area("Ghi chú (thêm lý do sửa/loại ở cuối)", q.get("ghi_chu", ""), height=80)
        trang_thai = st.radio("Trạng thái", list(TRANG_THAI), format_func=TRANG_THAI.get, horizontal=True,
                              index=list(TRANG_THAI).index(q.get("trang_thai", "chua_duyet")))
        b1, b2 = st.columns(2)
        luu = b1.form_submit_button("💾 Lưu", use_container_width=True, type="primary")
        luu_tiep = b2.form_submit_button("💾 Lưu và sang câu sau", use_container_width=True)

    if luu or luu_tiep:
        try:
            moi = dict(q)
            moi.update({"cau_hoi": cau_hoi.strip(), "dap_an": dap_an.strip(), "so_tien": so_nguyen(so_tien),
                        "diem_tru": int(diem) if diem.strip() else None, "gold_ids": ds_ma(gold),
                        "can_cu": can_cu.strip(), "ghi_chu": ghi_chu.strip(), "trang_thai": trang_thai})
            if ds_ma(nsd):
                moi["nguon_sua_doi"] = ds_ma(nsd)
            else:
                moi.pop("nguon_sua_doi", None)
            if trang_thai != "chua_duyet":
                moi["nguoi_duyet"] = nguoi
            if trang_thai == "dat" and any(moi[k] != q.get(k) for k in ("cau_hoi", "dap_an", "so_tien", "diem_tru", "gold_ids")):
                moi["trang_thai"] = "da_sua"
                st.info("Có sửa nội dung nên trạng thái được chuyển thành Đã sửa.")
            loi, _ = kiem_tra(moi, tat_ca)
            if loi and trang_thai != "loai":
                st.error("Chưa lưu: " + "; ".join(loi))
            else:
                luu_cau(moi)
                st.toast(f"Đã lưu {qid}", icon="✅")
                if luu_tiep and i < len(ids) - 1:
                    st.session_state.chuyen_toi = ids[i + 1]
                time.sleep(0.4)
                st.rerun()
        except ValueError as e:
            st.error(f"Chưa lưu: {e}")

with phai:
    st.subheader("Điều khoản căn cứ")
    loi, cb = kiem_tra(q, tat_ca)
    for m in loi:
        st.error(m)
    for m in cb:
        st.warning(m)
    if not loi and not cb:
        st.success("Kiểm tra tự động: không thấy vấn đề (vẫn cần đọc lại nội dung)")
    by, con = kho()
    for g in (q.get("gold_ids") or []) + (q.get("nguon_sua_doi") or []):
        if g not in by:
            continue
        v = phien_ban(g, q["ngay_ap_dung"])
        nhan = f"{g}" + ("" if v else " — không có hiệu lực vào ngày này")
        with st.expander(nhan, expanded=True):
            v = v or by[g][-1]
            st.caption(v.get("ngu_canh") or "")
            cha = phien_ban(v["parent_id"], q["ngay_ap_dung"])
            if cha and v["cap"] == "Diem":
                st.markdown(f"*Câu dẫn khoản:* {cha['noi_dung']}")
            st.markdown(v["noi_dung"])
            for c in con.get(g, [])[:12]:
                cv = phien_ban(c, q["ngay_ap_dung"])
                if cv:
                    st.markdown(f"- `{c.rsplit('.', 1)[-1]}` {cv['noi_dung']}")
            if len(by[g]) > 1:
                st.caption("Các phiên bản: " + " · ".join(
                    f"{x['hieu_luc_tu']} → {x['hieu_luc_den'] or 'nay'}" + (f" ({x['nguon_sua_doi']})" if x.get("nguon_sua_doi") else "")
                    for x in by[g]))

    with st.expander("Tra cứu điều khoản khác"):
        tu = st.text_input("Mã (ND168_2024.D6.K9) hoặc từ khóa", key="tra")
        if tu.strip():
            if tu.strip() in by:
                kq = [tu.strip()] + con.get(tu.strip(), [])
            else:
                ks = tu.lower().split()
                kq = [uid for uid, vs in by.items() if all(k in vs[-1]["noi_dung"].lower() for k in ks)][:20]
            for uid in kq:
                v = phien_ban(uid, q["ngay_ap_dung"]) or by[uid][-1]
                st.markdown(f"**`{uid}`** {v['noi_dung'][:300]}")
            if not kq:
                st.caption("Không tìm thấy")
