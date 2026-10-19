"""Bước 2: trích dẫn chiếu và quan hệ sửa đổi -> references.jsonl, amendments.jsonl

Phụ trách: TV2.   Chạy: python scripts/02_extract_relations.py
Dùng graphrag.parsing.reference_extractor và graphrag.parsing.amendment_parser.
"""
from __future__ import annotations


def main() -> None:
    # TODO(TV2):
    # 1. Đọc data/processed/corpus.jsonl
    # 2. reference_extractor: tìm "khoản 2 Điều 6 của Nghị định này"... -> cạnh THAM_CHIEU / HUONG_DAN
    # 3. amendment_parser: văn bản sửa đổi (L118, ND184, ND236, TT13) -> SUA_DOI / BO_SUNG / THAY_THE / BAI_BO
    #    kèm ngay_hieu_luc; đồng thời cập nhật hieu_luc_den cho phiên bản cũ trong corpus
    raise NotImplementedError


if __name__ == "__main__":
    main()
