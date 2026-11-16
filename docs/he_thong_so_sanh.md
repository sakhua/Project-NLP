# Ba hệ thống được so sánh

Cập nhật 05/11/2026. Dùng khi viết phần Phương pháp và Thực nghiệm của báo cáo môn NLP.

## Tóm tắt

| | B1 – Hybrid RAG | B2 – GraphRAG kiểu Microsoft | Đề xuất – Hybrid GraphRAG |
|---|---|---|---|
| Mã trong code | `hybrid_rag` | `ms_graphrag` | `hybrid_graphrag` |
| Tìm điều khoản | BM25 + vector (bge-m3), RRF, rerank | không tìm trực tiếp: đi qua thực thể | BM25 + vector, RRF, rerank |
| Đồ thị | không | đồ thị thực thể do LLM trích + cộng đồng Leiden + báo cáo cộng đồng | đồ thị văn bản: dẫn chiếu, hướng dẫn, cha–con |
| Dựng đồ thị | – | LLM (gpt-4o-mini), ~3.000 lượt gọi, có chi phí | luật (regex) trên cấu trúc văn bản, không tốn LLM |
| Ngữ cảnh cho LLM | 10 điều khoản | 10 điều khoản gắn với thực thể + mô tả thực thể, quan hệ, báo cáo cộng đồng | 10 điều khoản + tối đa 30 điều khoản mở rộng |
| Lọc theo ngày áp dụng | có | có (tắt được để chạy bản nguyên gốc) | có |
| Mô hình sinh, prompt, trích dẫn | chung | chung | chung |

Vì ba hệ thống dùng chung mô hình sinh, prompt, cách trích dẫn và lọc phiên bản theo ngày, khác biệt kết quả đến từ cách truy hồi:

- Đề xuất so với B1: tác dụng của bước mở rộng trên đồ thị văn bản (B1 chính là hệ thống đề xuất bỏ bước này).
- Đề xuất so với B2: đồ thị dựng từ cấu trúc pháp lý (rẻ, chính xác, giữ phiên bản) so với đồ thị thực thể do LLM trích (cách của Microsoft).

## B2 – GraphRAG kiểu Microsoft: cài đặt lại

Theo Edge và cộng sự (2024), *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*. Nhóm tự cài đặt
(không dùng thư viện `graphrag`) để dùng chung lọc ngày, cách trích dẫn và mô hình sinh với hai hệ thống còn lại.

Dựng chỉ mục (`scripts/05_ms_graphrag_index.py`, `graphrag/ms_graphrag/indexing.py`):

1. Đơn vị văn bản: mỗi phiên bản khoản/điểm kèm ngữ cảnh (bản gốc cắt theo token; ở đây giữ đơn vị pháp lý để trích dẫn được).
2. LLM trích thực thể và quan hệ. Có 8 loại thực thể riêng cho lĩnh vực: hành vi, phương tiện, chủ thể, chế tài, điều kiện, giấy tờ, cơ quan, khái niệm.
3. Gộp thực thể cùng tên, quan hệ cùng cặp; LLM tóm tắt khi có nhiều mô tả.
4. Phân cộng đồng phân cấp bằng Leiden: cộng đồng lớn hơn 10 thực thể được chia tiếp, tối đa 3 cấp.
5. LLM viết báo cáo cộng đồng (tiêu đề, tóm tắt, mức độ quan trọng, các phát hiện), từ cấp sâu nhất lên.
6. Embedding mô tả thực thể và tóm tắt cộng đồng.

Truy vấn (`graphrag/pipeline/ms_graphrag.py`):

- **Local search** (dùng để đánh giá):
  - 10 thực thể gần câu hỏi, cộng 10 thực thể lân cận theo trọng số quan hệ;
  - lấy quan hệ, 3 báo cáo cộng đồng và các điều khoản gắn với thực thể;
  - điều khoản xếp theo thứ hạng thực thể và lọc theo ngày;
  - sinh câu trả lời.
- **Global search** (chỉ để demo câu hỏi tổng quan):
  - chọn tối đa 24 báo cáo cộng đồng cấp 0 gần câu hỏi;
  - map: mỗi nhóm 6 báo cáo cho ra các ý có điểm;
  - reduce: lấy 20 ý tốt nhất để tổng hợp câu trả lời;
  - không trích mã điều khoản, không lọc theo ngày.

Tham số trong `configs/base.yaml`, mục `ms_graphrag`.

## Chạy

```
pip install -e ".[msgraph]"
python scripts/05_ms_graphrag_index.py --uoc-tinh        # đếm số lượt gọi LLM
python scripts/05_ms_graphrag_index.py --gioi-han 100    # thử 100 đơn vị, xem data/processed/ms_graphrag/thong_ke.md
python scripts/05_ms_graphrag_index.py                   # toàn bộ (chạy lại để làm tiếp nếu bị dừng)
python scripts/chay_bo_test.py --he-thong hybrid_graphrag hybrid_rag ms_graphrag --gioi-han 20
```

Báo cáo so sánh (`data/eval/ket_qua/bao_cao_*.md`) có:

- tỉ lệ câu Đúng theo loại câu của từng hệ thống;
- tỉ lệ ngữ cảnh đủ gold và recall trích dẫn;
- chênh lệch giữa hệ thống đề xuất và từng baseline, kiểm định bằng paired bootstrap.

Độ đo: chỉ dùng 6 độ đo không cần LLM chấm, xem `docs/do_do_danh_gia.md`.

## Thí nghiệm phụ (ablation) gợi ý

- B2 tắt lọc theo ngày (`use_temporal_filter=False`): GraphRAG nguyên bản không có khái niệm hiệu lực, nên kết quả câu hiệu lực sẽ kém đi.
- Hệ thống đề xuất với `hops = 2`, hoặc chỉ dùng cạnh THUOC (`use_references=False`).
