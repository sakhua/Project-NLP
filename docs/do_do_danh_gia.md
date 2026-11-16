# Độ đo đánh giá

Quyết định 05/11/2026: chỉ dùng **6 độ đo**, đều tính tự động bằng quy tắc. Không dùng LLM làm giám khảo, không dùng RAGAS.
Nhờ vậy kết quả tất định, lặp lại được, không tốn chi phí API.

Mã nguồn: `graphrag/evaluation/metrics.py`. Chạy: `scripts/chay_bo_test.py`.

## Ký hiệu

- *G*: tập mã điều khoản gold của câu hỏi (`gold_ids`).
- *R*: danh sách điều khoản hệ thống lấy ra, theo thứ tự xếp hạng (`retrieved_ids`). *R@k* là *k* phần tử đầu.
- *k* ∈ {5, 10, 40}. Với *k* = 40, hệ thống đề xuất dùng đúng ngân sách ngữ cảnh của mình (10 điều khoản tìm trực tiếp
  + tối đa 30 điều khoản mở rộng trên đồ thị). Hai baseline chỉ lấy 10 điều khoản, nên @40 của chúng bằng @10.
  So sánh @10 cho thấy chất lượng xếp hạng; so sánh @40 cho thấy phần đóng góp của mở rộng đồ thị.
- **Dữ kiện kiểm chứng được** trong một đoạn chữ: mỗi mức tiền (hiểu cả "18.000.000 đồng", "18 triệu", "từ 18 đến 20 triệu")
  và mỗi số điểm giấy phép lái xe ("trừ 04 điểm").

## Bốn độ đo truy hồi

| Độ đo | Công thức | Ý nghĩa |
|---|---|---|
| Recall@k | \|G ∩ R@k\| / \|G\| | Tỉ lệ điều khoản cần thiết được tìm thấy |
| Full Recall@k | 1 nếu G ⊆ R@k, ngược lại 0 | Có lấy đủ **mọi** căn cứ không. Quan trọng với câu multi-hop, ví dụ cần cả khoản mức phạt và khoản trừ điểm |
| MRR@k | 1 / thứ hạng của điều khoản gold đầu tiên trong R@k (0 nếu không có) | Căn cứ đúng được xếp cao đến đâu |
| F2@k | 5·P·R / (4·P + R), với P = \|G ∩ R@k\| / \|R@k\|, R = Recall@k | Cân bằng precision và recall, nghiêng về recall: thiếu căn cứ nặng hơn thừa ngữ cảnh |

## Hai độ đo câu trả lời

**Faithfulness**: câu trả lời có bám ngữ cảnh không, có bịa không.

- Các dữ kiện cần đối chiếu: mọi mức tiền, mọi số điểm trong câu trả lời, và mọi mã điều khoản được trích dẫn.
- Một dữ kiện **có căn cứ** khi:
  - mức tiền, số điểm có xuất hiện trong nội dung các điều khoản đã đưa cho LLM (kể cả câu dẫn của khoản);
  - mã trích dẫn là một điều khoản có trong ngữ cảnh.
- Faithfulness = số dữ kiện có căn cứ / tổng số dữ kiện.
- Câu trả lời không nêu dữ kiện nào thì không chấm (không tính vào trung bình).

**Answer Relevance**: câu trả lời có đáp đúng trọng tâm câu hỏi không, so với đáp án chuẩn.

- Đặt *A* là dữ kiện của câu trả lời, *D* là dữ kiện của đáp án chuẩn (gồm `so_tien`, số điểm trong `dap_an` và `diem_tru`).
- Answer Relevance = F1(*A*, *D*) = 2·P·R / (P + R), với P = \|A ∩ D\| / \|A\|, R = \|A ∩ D\| / \|D\|:
  - thiếu mức tiền hoặc số điểm thì R giảm;
  - nêu thêm mức tiền, số điểm không đúng thì P giảm.
- Khi đáp án chuẩn không có dữ kiện (ví dụ "chưa bị xử phạt vì quy định chưa có hiệu lực"), điểm là 1 nếu câu trả lời nói rõ
  là chưa/không áp dụng, ngược lại là 0. Nhờ vậy độ đo phản ánh cả tính đúng theo thời gian của các câu hiệu lực.

Hai độ đo bổ sung cho nhau. Faithfulness so câu trả lời với **ngữ cảnh**: hệ thống lấy nhầm phiên bản cũ rồi trả lời đúng theo
phiên bản đó thì vẫn đạt Faithfulness cao. Answer Relevance so với **đáp án chuẩn** nên bắt được lỗi đó.

## So sánh hệ thống

Mỗi độ đo lấy trung bình trên các câu, báo cáo theo từng loại câu (đơn, multi-hop, hiệu lực, so sánh) và cho toàn bộ.
Chênh lệch giữa hệ thống đề xuất và từng baseline được kiểm định bằng **paired bootstrap** (10.000 lần lấy mẫu lại theo câu).
Chênh lệch có ý nghĩa thống kê khi p < 0,05.

## Hạn chế cần nêu trong báo cáo

- **Hai độ đo câu trả lời chỉ xét dữ kiện có thể so khớp** (mức tiền, số điểm, mã điều khoản). Chúng không chấm cách diễn đạt,
  không chấm các hình thức xử phạt khác như tước giấy phép lái xe hay tịch thu.
- **Câu chỉ có mức phạt cá nhân:** câu trả lời nêu thêm mức phạt đối với tổ chức (đúng luật) vẫn bị giảm P của Answer Relevance.
- **Nên kiểm chứng bộ chấm tự động:** cả nhóm có thể chấm tay một mẫu nhỏ (khoảng 50 câu, Đúng / Một phần / Sai) rồi
  báo cáo mức khớp với bộ chấm tự động.
