# Hướng dẫn gán nhãn bộ câu hỏi đánh giá

Đề tài: Xây dựng hệ thống hỏi đáp pháp luật giao thông đường bộ Việt Nam dựa trên GraphRAG.
Phiên bản 1 – 19/10/2026. Người phụ trách: TV3. Mọi thành viên đọc hết trước khi soạn câu đầu tiên.

## 1. Mục đích và số lượng

Bộ câu hỏi dùng để so sánh 4 hệ thống (B1 BM25, B2 vector, B3 hybrid, GraphRAG) trên cùng một chuẩn.
Mỗi câu phải có **đáp án** và **mã điều khoản căn cứ (gold_ids)** chính xác, vì các độ đo Recall@k,
Full Recall@k, MRR@k, F2@k, Faithfulness và Answer Relevance (bản không dùng LLM, `docs/do_do_danh_gia.md`) đều được tính tự động từ các trường này.

| Mốc | Số câu mỗi người | Tổng |
|---|---|---|
| Tuần 3 (hết 25/10) | 15 | ~45 |
| Tuần 4 (hết 01/11) | +20 | ~105 |
| Tuần 5 (hết 08/11) | +20 | ~165 |
| Tuần 6 (chốt 15/11) | bổ sung cho đủ | ~200 |

Tỉ lệ theo loại (áp dụng cho từng người): **Đơn 30% · Multi-hop 30% · Hiệu lực thời gian 25% · So sánh 15%**.
Với 15 câu tuần này: 5 đơn, 4 multi-hop, 4 hiệu lực, 2 so sánh.

Phạm vi: chỉ hỏi những gì trả lời được từ 11 văn bản trong `data/manifest.csv` (không tính văn bản hợp nhất).
Ưu tiên các văn bản người dùng hay hỏi: NĐ 168/2024 (mức phạt, trừ điểm), Luật 36/2024, TT 38/2024 (tốc độ),
TT 65/2024 (phục hồi điểm), NĐ 151/2024.

## 2. Định dạng

Mỗi người soạn trong file riêng `data/eval/questions_TV1.jsonl` (TV2, TV3 tương tự).
**Mỗi dòng là một câu hỏi, một đối tượng JSON**, mã hóa UTF-8. Soạn bằng VS Code, không dùng Word/Excel.
Mẫu đầy đủ, đã kiểm tra mã: `data/eval/questions_template.jsonl`.

| Trường | Bắt buộc | Kiểu | Ý nghĩa |
|---|---|---|---|
| `id` | có | chuỗi | `q1001`… cho TV1, `q2001`… cho TV2, `q3001`… cho TV3. Không dùng lại id đã xóa |
| `loai` | có | chuỗi | `don`, `multi_hop`, `hieu_luc`, `so_sanh` (mục 3) |
| `ngay_ap_dung` | có | `YYYY-MM-DD` | Ngày xảy ra tình huống được hỏi (mục 5) |
| `cau_hoi` | có | chuỗi | Câu hỏi bằng tiếng Việt tự nhiên (mục 4) |
| `dap_an` | có | chuỗi | Đáp án chuẩn, ngắn gọn, đủ ý (mục 6) |
| `so_tien` | có | danh sách số nguyên | Mọi mức tiền trong đáp án, đơn vị đồng: `[18000000, 20000000]`. Không có thì `[]` |
| `diem_tru` | có | số nguyên hoặc `null` | Số điểm GPLX bị trừ. Không có thì `null` |
| `gold_ids` | có | danh sách mã | Các đơn vị căn cứ, mã đúng như trong `corpus.jsonl` (mục 7) |
| `can_cu` | có | chuỗi | Căn cứ viết cho người đọc: "điểm b khoản 9, điểm b khoản 16 Điều 6 NĐ 168/2024" |
| `nguoi_soan` | có | chuỗi | `TV1` / `TV2` / `TV3` |
| `nguon` | có | chuỗi | `tu_viet` (tự đặt) · `llm_nhap` (LLM gợi ý, người sửa lại) · `vlsp` (lấy ý từ VLSP 2025) |
| `nguon_sua_doi` | không | danh sách mã | Khi đáp án dựa vào nội dung đã sửa đổi: mã đơn vị của **văn bản sửa đổi** chứa nội dung mới, vd. `["ND238_2026.D2.K2"]` (mục 7) |
| `cap_voi` | không | chuỗi | Với câu hiệu lực: id của câu cùng nội dung nhưng khác ngày |
| `ghi_chu` | không | chuỗi | Giả định đã dùng, điểm còn băn khoăn |

## 3. Bốn loại câu hỏi

### 3.1. Đơn – `don` (30%)
Trả lời được từ **một Điều** của **một văn bản** (có thể gồm khoản xử phạt và khoản trừ điểm trong cùng Điều).

> Người điều khiển xe ô tô không chấp hành hiệu lệnh của đèn tín hiệu giao thông bị phạt bao nhiêu tiền và bị trừ mấy điểm?
> → Phạt 18.000.000–20.000.000 đồng; trừ 4 điểm GPLX. Gold: `ND168_2024.D6.K9.b`, `ND168_2024.D6.K16.b`

### 3.2. Multi-hop – `multi_hop` (30%)
Phải **nối từ hai Điều trở lên**, thường ở hai văn bản khác nhau (luật ↔ nghị định ↔ thông tư),
hoặc phải đi theo một dẫn chiếu "theo quy định tại khoản… Điều…". Câu hỏi **không được nêu sẵn** con số trung gian.

> Ô tô chạy 160 km/h trên đường cao tốc thì bị xử phạt thế nào?
> → Tốc độ tối đa trên cao tốc là 120 km/h (TT 38) nên vượt 40 km/h, thuộc mức "trên 35 km/h": phạt 12.000.000–14.000.000 đồng, trừ 6 điểm.
> Gold: `TT38_2024.D9.K2`, `ND168_2024.D6.K7.a`, `ND168_2024.D6.K16.c`

### 3.3. Hiệu lực thời gian – `hieu_luc` (25%)
Đáp án **thay đổi theo ngày áp dụng** vì có văn bản sửa đổi, quy định có hiệu lực muộn hơn, hoặc điều khoản chuyển tiếp.
**Luôn soạn theo cặp**: cùng câu hỏi, hai ngày áp dụng ở hai phía của mốc thay đổi, hai đáp án khác nhau; ghi `cap_voi` cho nhau.

> (ngày 2025-10-01) Lái ô tô chở cháu 8 tuổi, cao 1,2 m ngồi ghế trước cạnh người lái thì bị xử phạt thế nào?
> → Chưa bị xử phạt về hành vi này: quy định tại điểm m khoản 3 Điều 6 NĐ 168 chỉ có hiệu lực từ 01/01/2026.
> Gold: `ND168_2024.D6.K3.m`, `ND168_2024.D53.K2`
>
> (ngày 2026-09-01) cùng câu hỏi → Phạt 800.000–1.000.000 đồng theo điểm m khoản 3 Điều 6 NĐ 168, đã được NĐ 238/2026 sửa đổi.
> Gold: `ND168_2024.D6.K3`, `ND168_2024.D6.K3.m` · `nguon_sua_doi`: `ND238_2026.D2.K2`

Nguồn gợi ý cho loại này (đã ghi trong `ghi_chu` của `data/manifest.csv`):
NĐ 238/2026 sửa NĐ 168 (từ 15/08/2026, có điểm lùi tới 2028–2029) · Luật 118/2025 sửa Luật 36 (từ 01/07/2026) ·
NĐ 184/2025, NĐ 236/2026 sửa NĐ 151 · TT 13/2025 rồi TT 105/2026 sửa TT 65 (kiểm tra phục hồi điểm, mốc 01/03/2025, 01/07/2026, 01/07/2027).

### 3.4. So sánh / hệ quả – `so_sanh` (15%)
So sánh hai đối tượng (ô tô và xe máy, hai mức tốc độ…) hoặc hỏi đủ các hệ quả của một hành vi (phạt tiền + trừ điểm + tước GPLX + biện pháp khắc phục).

> Cùng lỗi vượt đèn đỏ, ô tô và xe máy bị phạt khác nhau thế nào?
> → Ô tô: 18.000.000–20.000.000 đồng, trừ 4 điểm. Xe máy: 4.000.000–6.000.000 đồng, trừ 4 điểm.
> Gold: `ND168_2024.D6.K9.b`, `ND168_2024.D6.K16.b`, `ND168_2024.D7.K7.c`, `ND168_2024.D7.K13.b`

## 4. Viết câu hỏi

1. Viết như **người dân hỏi**: dùng từ đời thường ("vượt đèn đỏ", "xe máy", "bằng lái"), không chép lại câu chữ trong luật.
2. **Không nêu số điều, khoản, tên văn bản** trong câu hỏi (trừ khi chính câu hỏi là "Điều X quy định gì").
3. Tình huống phải **đủ rõ để chỉ có một đáp án**: nêu loại xe, hành vi, con số (tốc độ, nồng độ cồn…). Thiếu dữ kiện thì ghi giả định vào `ghi_chu`.
4. Một câu hỏi một tình huống; không gộp hai câu hỏi không liên quan.
5. Đa dạng chủ đề: không quá 3 câu cùng một Điều trong file của mỗi người.
6. Không hỏi điều nằm ngoài 11 văn bản (biển báo dạng hình ảnh, trách nhiệm hình sự, thủ tục của địa phương).

## 5. Ngày áp dụng

- Bắt buộc với mọi câu. Câu không phụ thuộc thời gian: dùng **2026-10-01** cho thống nhất.
- Câu `hieu_luc`: chọn hai ngày cách mốc thay đổi ít nhất vài tuần để tránh tranh cãi về ngày bắt đầu (ví dụ mốc 15/08/2026 → chọn 2026-06-01 và 2026-09-01).
- Không chọn ngày trước 01/01/2025 (trước khi các văn bản gốc có hiệu lực) và không sau 31/12/2029.

## 6. Viết đáp án

- Nêu đủ các ý mà câu hỏi đòi: mức phạt, số điểm trừ, hình thức bổ sung (tước GPLX…), điều kiện áp dụng.
- Viết tiền theo dạng `18.000.000–20.000.000 đồng`; đồng thời ghi số nguyên vào `so_tien` (dùng chấm điểm tự động).
- Nếu theo văn bản thì **không bị phạt / không có quy định**, viết rõ như vậy và vẫn ghi gold là điều khoản chứng minh điều đó.
- Không thêm lời khuyên, không bình luận ngoài nội dung văn bản.

## 7. Ghi `gold_ids`

1. Ghi **đơn vị nhỏ nhất đủ để trả lời**: có điểm thì ghi điểm (`ND168_2024.D6.K9.b`), khoản không có điểm thì ghi khoản, Điều không có khoản thì ghi Điều.
2. Ghi **mọi** đơn vị cần thiết, kể cả khoản trừ điểm, khoản quy định tốc độ, khoản quy định hiệu lực. Thiếu một mã là Full Recall bị tính sai.
3. Nếu mức tiền nằm ở **câu dẫn của khoản** và hành vi nằm ở **điểm**, chỉ cần ghi mã điểm (hệ thống đã gắn câu dẫn vào điểm); với câu `hieu_luc` sau sửa đổi thì ghi thêm mã khoản để rõ căn cứ mức tiền.
4. Nội dung đến từ **văn bản sửa đổi** (thiết kế phiên bản: `docs/thiet_ke_do_thi.md`):
   - `gold_ids` ghi **mã của văn bản bị sửa** (`ND168_2024.D6.K3.m`), vì hệ thống lưu mọi phiên bản dưới cùng một mã
     và lọc theo ngày áp dụng. **Không** ghi mã của văn bản sửa đổi vào `gold_ids`.
   - Ghi mã đơn vị của văn bản sửa đổi chứa câu lệnh/nội dung mới vào `nguon_sua_doi` (`["ND238_2026.D2.K2"]`).
   - Khoản/điểm **được bổ sung mới** dùng mã mới theo văn bản bị sửa: "Bổ sung khoản 1a vào trước khoản 1 Điều 6"
     → `ND168_2024.D6.K1a`; "Bổ sung điểm k1 vào sau điểm k khoản 4 Điều 41" → `ND168_2024.D41.K4.k1`.
     Mã này chưa có trong `corpus.jsonl` cho tới khi bước 2 xử lý xong sửa đổi; `check_questions.py` chỉ cảnh báo nếu đã ghi `nguon_sua_doi`.
   - Câu hỏi trước mốc sửa đổi (bản gốc còn hiệu lực) thì không cần `nguon_sua_doi`.
5. Mã phải tồn tại trong `data/processed/corpus.jsonl` (hoặc `versions.jsonl`, trừ trường hợp mã bổ sung ở trên). Tra cứu bằng:

```
python scripts/tim_dieu_khoan.py "đèn tín hiệu" --van-ban ND168_2024
python scripts/tim_dieu_khoan.py "cao tốc" "120"
python scripts/tim_dieu_khoan.py --ma ND168_2024.D6.K16
```

## 8. Dùng LLM để gợi ý (được phép, có điều kiện)

LLM chỉ dùng để **gợi ý câu hỏi**; đáp án và gold **phải tự tra và kiểm tra trên văn bản**. Ghi `"nguon": "llm_nhap"`.
Gợi ý câu lệnh:

```
Dưới đây là một điều khoản luật giao thông Việt Nam. Hãy viết 3 câu hỏi mà người dân bình thường
có thể hỏi, dùng từ ngữ đời thường, không nhắc số điều khoản, mỗi câu nêu tình huống cụ thể.
[dán ngu_canh + noi_dung của điều khoản]
```

Không dùng LLM để sinh đáp án: đáp án do LLM viết dễ sai mức tiền và sẽ làm sai lệch đánh giá.

## 9. Quy trình và kiểm tra

1. Soạn trong `data/eval/questions_TVx.jsonl`.
2. Chạy kiểm tra, sửa đến khi không còn lỗi:
   ```
   python scripts/check_questions.py data/eval/questions_TV1.jsonl
   ```
   Script báo: thiếu trường, sai loại, sai định dạng ngày, id trùng, **mã gold không có trong corpus**,
   số tiền trong `so_tien` không xuất hiện trong nội dung các gold, câu `hieu_luc` thiếu cặp, và thống kê tỉ lệ các loại.
3. Đẩy lên nhánh riêng, mở Pull Request; người khác đọc chéo 5 câu ngẫu nhiên.
4. Tuần 5: hai người gán độc lập cùng 50 câu (chỉ đáp án và gold) để đo mức đồng thuận.
5. Tuần 6: nhóm trưởng gộp thành `data/eval/questions.jsonl` và chốt bộ câu hỏi.

## 10. Checklist trước khi đẩy lên

- [ ] Câu hỏi đọc lên tự nhiên, không chứa số điều khoản
- [ ] Đáp án đã đối chiếu trực tiếp với văn bản (không lấy từ báo, mạng xã hội hay LLM)
- [ ] Mọi mức tiền trong đáp án có trong `so_tien`; `diem_tru` đúng
- [ ] Đủ gold, mã tra được bằng `tim_dieu_khoan.py`
- [ ] Câu `hieu_luc` có cặp, hai đáp án thật sự khác nhau
- [ ] `check_questions.py` không báo lỗi
