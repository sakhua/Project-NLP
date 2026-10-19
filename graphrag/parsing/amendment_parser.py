"""Phân tích văn bản sửa đổi → quan hệ SUA_DOI / BO_SUNG / THAY_THE / BAI_BO.

Phụ trách: TV2 (tuần 4). Kết quả: data/processed/amendments.jsonl
  {"src": "ND238_2026.D7.K1", "dst": "ND168_2024.D6.K5", "type": "SUA_DOI",
   "ngay_hieu_luc": "2026-08-15", "noi_dung_moi": "..."}

Cặp văn bản cần xử lý (theo manifest.csv):
  ND238_2026 → ND168_2024
  L118_2025  → L36_2024   (chỉ phần sửa Luật TTATGT)
  ND184_2025 → ND151_2024 (chỉ các điều sửa NĐ 151)
  ND236_2026 → ND151_2024
  TT13_2025  → TT65_2024  (Điều 6)

Mẫu câu thường gặp:
  "Sửa đổi, bổ sung khoản 5 Điều 6 như sau:"
  "Bổ sung điểm đ vào sau điểm d khoản 2 Điều 7 như sau:"
  "Bãi bỏ điểm c khoản 3 Điều 9."
  "Thay thế cụm từ “...” bằng cụm từ “...” tại ..."
Toàn bộ kết quả phải được kiểm tra thủ công (số lượng ít).
"""
from __future__ import annotations


def parse_amendments(amending_doc_id: str, target_doc_id: str, effective_date: str) -> list[dict]:
    # TODO(TV2)
    raise NotImplementedError
