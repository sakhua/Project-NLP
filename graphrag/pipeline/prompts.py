"""Prompt sinh câu trả lời có trích dẫn và hàm tách trích dẫn. Phụ trách: TV1.

Dùng chung cho mọi hệ thống (B1–B3, GraphRAG) để so sánh công bằng: chỉ khác phần NGỮ CẢNH.
Thử nhanh trên câu hỏi mẫu với ngữ cảnh chuẩn (gold): python scripts/thu_prompt.py
"""
from __future__ import annotations

import re
from datetime import date

from graphrag.common.ids import base_id, parse_id

SYSTEM = """Bạn là trợ lý tra cứu pháp luật giao thông đường bộ Việt Nam. Bạn trả lời câu hỏi của người dân \
CHỈ dựa trên các điều khoản trong phần NGỮ CẢNH, đúng với NGÀY ÁP DỤNG.

Quy tắc:
1. Chỉ dùng thông tin trong NGỮ CẢNH. Không dùng hiểu biết bên ngoài, không tự suy ra mức phạt không có trong NGỮ CẢNH.
2. Các điều khoản trong NGỮ CẢNH là phiên bản đang có hiệu lực tại NGÀY ÁP DỤNG. Điều khoản ghi "đã được … sửa đổi" \
là nội dung sau sửa đổi; khi dùng điều khoản đó, nói rõ là đã được sửa đổi.
3. Sau mỗi ý, ghi căn cứ bằng mã trong ngoặc vuông, đúng như mã ở đầu điều khoản, ví dụ [ND168_2024.D6.K9.b]. \
Nhiều căn cứ thì ghi [mã 1][mã 2]. Chỉ dùng mã có trong NGỮ CẢNH.
4. Câu hỏi về vi phạm: nêu đủ những gì NGỮ CẢNH có: mức phạt tiền, trừ điểm giấy phép lái xe, tước quyền sử dụng \
giấy phép, tịch thu, biện pháp khắc phục. Viết tiền dạng 18.000.000 – 20.000.000 đồng.
5. Câu hỏi cần nhiều bước (ví dụ tốc độ tối đa → mức vượt → mức phạt): nêu ngắn từng bước, mỗi bước có căn cứ.
6. Nếu NGỮ CẢNH cho biết quy định chưa có hiệu lực hoặc đã hết hiệu lực tại NGÀY ÁP DỤNG, nói rõ điều đó. \
Nếu NGỮ CẢNH không có quy định điều chỉnh tình huống, trả lời: "Không tìm thấy quy định áp dụng trong các văn bản \
được cung cấp." Không đoán.
7. Trả lời bằng tiếng Việt: câu đầu là kết luận ngắn; sau đó các ý chi tiết dạng gạch đầu dòng. \
Không thêm lời khuyên hay bình luận ngoài văn bản."""

USER_TEMPLATE = """NGÀY ÁP DỤNG: {ngay}

NGỮ CẢNH ({n} điều khoản):
{context}
{notes}
CÂU HỎI: {question}"""

NOTES_HEADER = """
GHI CHÚ HIỆU LỰC (các điều khoản liên quan nhưng KHÔNG có hiệu lực tại NGÀY ÁP DỤNG, không được dùng làm căn cứ áp dụng):
"""

_CAP = {"Diem": "điểm", "Khoan": "khoản", "Dieu": "Điều"}


def ngay_vn(d) -> str:
    """date hoặc 'YYYY-MM-DD' -> 'dd/mm/yyyy'."""
    if d is None:
        return ""
    d = date.fromisoformat(str(d)[:10]) if not isinstance(d, date) else d
    return d.strftime("%d/%m/%Y")


_LOAI = {"L": "Luật", "ND": "Nghị định", "TT": "Thông tư", "VBHN": "Văn bản hợp nhất"}


def ten_van_ban_ngan(doc_id: str) -> str:
    """'ND238_2026' -> 'Nghị định 238/2026' (khi không có tên đầy đủ trong ngu_canh)."""
    m = re.match(r"^([A-Z]+)(\d+)_(\d{4})$", doc_id)
    return f"{_LOAI.get(m.group(1), m.group(1))} {m.group(2)}/{m.group(3)}" if m else doc_id


def ten_dieu_khoan(uid: str, ten_van_ban: str | None = None) -> str:
    """'ND168_2024.D6.K3.m' -> 'điểm m khoản 3 Điều 6 Nghị định 168/2024/NĐ-CP' (dùng để hiển thị, đặt trong prompt)."""
    p = parse_id(base_id(uid))
    parts = []
    if p.diem:
        parts.append(f"điểm {p.diem}")
    if p.khoan:
        parts.append(f"khoản {p.khoan}")
    if p.dieu:
        parts.append(f"Điều {p.dieu}")
    if p.chuong:
        parts.append(f"Chương {p.chuong}")
    parts.append(ten_van_ban or ten_van_ban_ngan(p.doc))
    return " ".join(parts)


_LOAI_NGAN = {"L": "Luật", "ND": "NĐ", "TT": "TT", "VBHN": "VBHN"}


def nhan_ngan(uid: str) -> str:
    """Nhãn ngắn để vẽ đồ thị, gắn chip trích dẫn: 'ND168_2024.D6.K9.b' -> 'Đ6.K9.b · NĐ 168/2024'."""
    try:
        p = parse_id(base_id(uid))
    except ValueError:
        return uid
    m = re.match(r"^([A-Z]+)(\d+)_(\d{4})$", p.doc)
    doc = f"{_LOAI_NGAN.get(m.group(1), m.group(1))} {m.group(2)}/{m.group(3)}" if m else p.doc
    if p.chuong:
        return f"Chương {p.chuong} · {doc}"
    parts = [x for x in (f"Đ{p.dieu}" if p.dieu else None, f"K{p.khoan}" if p.khoan else None, p.diem) if x]
    return f"{'.'.join(parts)} · {doc}" if parts else doc


def _ten_van_ban(u: dict) -> str | None:
    """Lấy 'Nghị định 168/2024/NĐ-CP' từ ngu_canh ('Nghị định 168/2024/NĐ-CP, Điều 6. …')."""
    nc = u.get("ngu_canh") or ""
    return nc.split(", Điều")[0] or None


def format_context(units: list[dict]) -> str:
    """units: các phiên bản đã lọc theo ngày (postgres.fetch_valid), mỗi phần tử có
    id, noi_dung, ngu_canh, hieu_luc_tu, hieu_luc_den, nguon_sua_doi (tùy chọn).

    Mỗi điều khoản gồm: mã, tên đọc được, hiệu lực, nguồn sửa đổi, đường dẫn (ngu_canh) và nội dung.
    Đường dẫn bắt buộc phải có: điểm a), b) chỉ có mức phạt ở câu dẫn của khoản.
    """
    blocks = []
    for u in units:
        meta = [ten_dieu_khoan(u["id"], _ten_van_ban(u))]
        if u.get("hieu_luc_tu"):
            hl = f"hiệu lực từ {ngay_vn(u['hieu_luc_tu'])}"
            if u.get("hieu_luc_den"):
                hl += f" đến hết ngày trước {ngay_vn(u['hieu_luc_den'])}"
            meta.append(hl)
        if u.get("nguon_sua_doi"):
            meta.append(f"đã được {ten_dieu_khoan(u['nguon_sua_doi'])} sửa đổi, bổ sung")
        lines = [f"[{base_id(u['id'])}] " + " · ".join(meta)]
        if u.get("ngu_canh"):
            lines.append(f"Thuộc: {u['ngu_canh']}")
        lines.append(f"Nội dung: {u['noi_dung']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_notes(notes: list[dict] | None) -> str:
    """notes: [{id, trang_thai: 'chua_hieu_luc'|'het_hieu_luc', ngay, noi_dung}] (graph_rag._validity_notes)."""
    if not notes:
        return ""
    lines = []
    for n in notes:
        ten = ten_dieu_khoan(n["id"])
        if n["trang_thai"] == "chua_hieu_luc":
            lines.append(f"- {ten}: chưa có hiệu lực, có hiệu lực từ ngày {ngay_vn(n['ngay'])}. Nội dung: {n['noi_dung']}")
        else:
            lines.append(f"- {ten}: đã hết hiệu lực từ ngày {ngay_vn(n['ngay'])}.")
    return NOTES_HEADER + "\n".join(lines) + "\n"


def build_user(question: str, ngay, units: list[dict], notes: list[dict] | None = None, extra: str = "") -> str:
    """extra: phần ngữ cảnh bổ sung đặt sau ghi chú hiệu lực (baseline GraphRAG dùng cho thực thể, quan hệ, cộng đồng)."""
    return USER_TEMPLATE.format(ngay=ngay_vn(ngay), n=len(units), context=format_context(units),
                                notes=format_notes(notes) + (extra or ""), question=question)


_BRACKET = re.compile(r"\[([^\[\]]{3,200})\]")
_ID_IN = re.compile(r"[A-Z]+\d+_\d{4}(?:\.[A-Za-z]?\d+[a-z]?|\.[a-zđ]\d?)*")


def parse_citations(answer: str, allowed: list[str] | set[str] | None = None) -> tuple[list[str], list[str]]:
    """Tách các mã trong ngoặc vuông của câu trả lời.

    Trả về (mã hợp lệ có trong `allowed`, mã lạ: không có trong ngữ cảnh hoặc sai cú pháp), giữ thứ tự, bỏ trùng.
    `allowed` = None thì mọi mã đúng cú pháp đều hợp lệ.
    """
    allowed_set = {base_id(a) for a in allowed} if allowed is not None else None
    ok, la = [], []
    for m in _BRACKET.finditer(answer):
        for raw in _ID_IN.findall(m.group(1)):
            uid = base_id(raw)
            try:
                parse_id(uid)
            except ValueError:
                target = la
            else:
                target = ok if allowed_set is None or uid in allowed_set else la
            if uid not in ok and uid not in la:
                target.append(uid)
    return ok, la
