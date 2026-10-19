"""Nhận diện và chuẩn hóa dẫn chiếu pháp lý thành mã định danh đích.

Phụ trách: TV2 (tuần 4). Kết quả: data/processed/references.jsonl
  {"src": "ND168_2024.D6.K5.a", "dst": "L36_2024.D10.K1", "type": "THAM_CHIEU", "text": "..."}

Các dạng cần xử lý (bổ sung khi khảo sát thêm):
  "điểm a khoản 2 Điều 5"                 → tương đối, cùng văn bản
  "khoản 3 Điều này"                       → tương đối, cùng Điều
  "Điều 6 Nghị định này"                   → cùng văn bản
  "Luật Trật tự, an toàn giao thông đường bộ" / "Luật số 36/2024/QH15" → văn bản khác
"""
from __future__ import annotations

import re

RE_REF = re.compile(
    r"(?:điểm\s+(?P<diem>[a-zđ])\s+)?"
    r"(?:khoản\s+(?P<khoan>\d+)\s+)?"
    r"Điều\s+(?P<dieu>\d+[a-z]?|này)"
    r"(?:\s+(?P<doc>(?:của\s+)?(?:Luật|Nghị định|Thông tư)\s+(?:này|số\s+[\w/\-Đđ]+)))?",
    re.IGNORECASE,
)

# Ánh xạ số hiệu → mã văn bản (đồng bộ với data/manifest.csv)
SO_HIEU_TO_ID = {
    "36/2024/QH15": "L36_2024",
    "118/2025/QH15": "L118_2025",
    "168/2024/NĐ-CP": "ND168_2024",
    "238/2026/NĐ-CP": "ND238_2026",
    "151/2024/NĐ-CP": "ND151_2024",
    "184/2025/NĐ-CP": "ND184_2025",
    "236/2026/NĐ-CP": "ND236_2026",
    "38/2024/TT-BGTVT": "TT38_2024",
    "65/2024/TT-BCA": "TT65_2024",
    "13/2025/TT-BCA": "TT13_2025",
    "105/2026/TT-BCA": "TT105_2026",
}


def find_references(text: str, current_id: str) -> list[dict]:
    """Tìm các dẫn chiếu trong `text` của đơn vị `current_id`, trả về danh sách cạnh."""
    # TODO(TV2): giải quyết "này", văn bản khác, dẫn chiếu ra ngoài phạm vi (gắn nhãn ngoai_pham_vi)
    raise NotImplementedError
