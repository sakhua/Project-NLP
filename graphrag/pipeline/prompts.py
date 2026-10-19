"""Prompt sinh câu trả lời có trích dẫn. Phụ trách: TV1."""

SYSTEM = (
    "Bạn là trợ lý tra cứu pháp luật giao thông đường bộ Việt Nam. "
    "Chỉ trả lời dựa trên các điều khoản được cung cấp trong NGỮ CẢNH. "
    "Mỗi ý trong câu trả lời phải ghi rõ căn cứ dạng [mã điều khoản]. "
    "Nếu ngữ cảnh không đủ để trả lời, hãy nói rõ là không đủ căn cứ."
)

USER_TEMPLATE = """NGÀY ÁP DỤNG: {ngay}

NGỮ CẢNH:
{context}

CÂU HỎI: {question}

Trả lời ngắn gọn, nêu mức phạt, số điểm bị trừ (nếu có) và căn cứ pháp lý."""


def format_context(units: list[dict]) -> str:
    """units: [{'id','noi_dung','hieu_luc_tu','hieu_luc_den'}, ...]"""
    lines = []
    for u in units:
        hl = f"hiệu lực từ {u.get('hieu_luc_tu')}" + (f" đến {u['hieu_luc_den']}" if u.get("hieu_luc_den") else "")
        lines.append(f"[{u['id']}] ({hl})\n{u['noi_dung']}")
    return "\n\n".join(lines)
