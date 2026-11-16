"""Chi tiết của từng bước trong tab "Quy trình" (bấm vào tên bước để xem).

Mỗi sự kiện step có thể kèm khóa `chi_tiet`:
  {"thuat_toan": [câu mô tả từng ý],
   "tham_so": [[tên, giá trị], ...],
   "bang": [{"tieu_de", "cot": [tên cột], "dong": [{"o": [ô], "id", "noi_dung", "kieu"}], "ghi_chu"}]}
`kieu` của dòng: "giu" (được chọn, in đậm), "bo" (bị loại, làm mờ) hoặc None.
Giao diện hiển thị chung mọi bước nên mỗi hệ thống chỉ cần dựng dữ liệu theo dạng này.
"""
from __future__ import annotations

from graphrag.pipeline import prompts


def nhan(uid: str | None) -> str:
    return prompts.nhan_ngan(uid) if uid else ""


def trich(text: str | None, n: int = 320) -> str | None:
    if not text:
        return None
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "…"


def so(x, nd: int = 4):
    return None if x is None else round(float(x), nd)


def dong(o: list, id: str | None = None, noi_dung: str | None = None, kieu: str | None = None) -> dict:
    return {"o": o, "id": id, "noi_dung": trich(noi_dung), "kieu": kieu}


def bang(tieu_de: str, cot: list[str], dong_: list[dict], ghi_chu: str | None = None) -> dict:
    return {"tieu_de": tieu_de, "cot": cot, "dong": dong_, "ghi_chu": ghi_chu}


def ct(thuat_toan: list[str], tham_so: list[list] | None = None, bang_: list[dict] | None = None) -> dict:
    return {"thuat_toan": thuat_toan, "tham_so": [[k, v] for k, v in (tham_so or []) if v not in (None, "")],
            "bang": [b for b in (bang_ or []) if b and b["dong"]]}


def sinh(cfg: dict, n_ky_tu: int, citations: list[str], unknown: list[str], allowed: list[str]) -> dict:
    """Bước sinh câu trả lời, dùng chung cho ba hệ thống."""
    c = cfg["llm"]
    dong_ = [dong([nhan(i), prompts.ten_dieu_khoan(i), "Hợp lệ"], i, kieu="giu") for i in citations]
    dong_ += [dong([i, "", "Mã lạ (không có trong ngữ cảnh)"], kieu="bo") for i in unknown]
    return ct(
        ["Gửi cho LLM: prompt hệ thống (chỉ được dùng ngữ cảnh, phải trích mã điều khoản trong ngoặc vuông) "
         "và prompt người dùng (câu hỏi, ngày áp dụng, các điều khoản trong ngữ cảnh, ghi chú hiệu lực).",
         "Tách các mã trong ngoặc vuông của câu trả lời. Mã có trong ngữ cảnh là trích dẫn hợp lệ; "
         "mã không có trong ngữ cảnh là mã lạ (mô hình tự đặt ra).",
         "Thứ tự gọi khóa: " + " → ".join(c.get("nha_cung_cap", ["openai", "openrouter"]))
         + " (khóa hết hạn mức thì chuyển sang khóa sau)."],
        [["Mô hình", c["model"]], ["Temperature", c.get("temperature", 0.0)], ["Tối đa token trả lời", c.get("max_tokens")],
         ["Độ dài prompt", f"{n_ky_tu:,} ký tự".replace(",", ".")], ["Số điều khoản được phép trích", len(allowed)]],
        [bang("Trích dẫn trong câu trả lời", ["Mã", "Điều khoản", "Kết quả"], dong_)])
