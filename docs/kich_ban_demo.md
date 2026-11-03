# Kịch bản demo hệ thống hỏi đáp GraphRAG

Thời lượng 10–12 phút, chạy hoàn toàn trên máy (Docker + backend + frontend), chỉ cần mạng cho OpenRouter.
Câu hỏi và đáp án đúng nằm trong `data/demo/cau_hoi_demo.json`; 6 câu đầu cũng có sẵn dạng nút bấm trên màn hình chào.

## 1. Chuẩn bị

### Hôm trước

1. Bật hệ thống: `powershell -ExecutionPolicy Bypass -File scripts\demo.ps1` (hoặc làm tay theo mục 6).
2. Chạy thử toàn bộ câu demo bằng pipeline thật:
   ```
   python scripts/kiem_tra_demo.py
   ```
   Mở `data/demo/ket_qua_chay_thu.md`, đọc từng câu trả lời và so với "Đáp án đúng".
   Câu nào **XEM LẠI** thì chạy lại 1–2 lần; vẫn sai thì bỏ khỏi kịch bản (D8 là câu khó, có thể bỏ).
3. Quay màn hình một lượt demo hoàn chỉnh (Win + G hoặc OBS) để dự phòng mất mạng, OpenRouter lỗi.
4. Nạp thêm tiền / kiểm tra hạn mức OpenRouter (cả buổi demo dưới 0,1 USD).

### 30 phút trước khi vào

| Việc | Lý do |
|---|---|
| Cắm sạc, tắt thông báo Windows (Focus assist), tắt Zalo/Messenger | Không bật thông báo giữa demo |
| Bật Docker Desktop, chạy `scripts\demo.ps1` | Backend dựng sẵn chỉ mục BM25 lúc khởi động |
| Hỏi 1 câu bất kỳ rồi xóa cuộc trò chuyện | "Làm nóng" kết nối OpenRouter, câu đầu tiên khi demo sẽ nhanh |
| Thanh bên: bấm biểu tượng thùng rác ở "Gần đây" để xóa lịch sử thử | Màn hình sạch |
| Chrome: F11 (toàn màn hình), Ctrl + `+` lên 110–125% nếu chiếu máy chiếu | Chữ đủ to cho người ngồi cuối |
| Kiểm tra góc trái dưới: PostgreSQL và Neo4j đều chấm xanh | Hai CSDL đã chạy |
| Mở sẵn tab thứ hai: video dự phòng | Chuyển ngay nếu có sự cố |
| Đăng nhập trước trang Thống kê (mật khẩu ADMIN_PASSWORD) | Không phải gõ mật khẩu trước lớp |

## 2. Kịch bản từng màn

Mỗi màn gồm **Bấm gì** và **Nói gì**. Phần in nghiêng là ý chính cần người xem nhớ.

### Màn 1. Giới thiệu (30 giây)

- **Bấm gì:** trang Trò chuyện, màn hình chào.
- **Nói gì:** "Hệ thống trả lời câu hỏi về luật giao thông dựa trên 12 văn bản: Luật 36/2024, Nghị định 168/2024 và các văn bản sửa đổi.
  Kho có hơn 3.000 điều khoản, 3.356 phiên bản theo thời gian và hơn 5.000 quan hệ trên đồ thị.
  *Mỗi câu trả lời đều có trích dẫn điều khoản và đúng với ngày áp dụng.*"

### Màn 2. Câu hỏi cơ bản: D1 (1 phút)

- **Bấm gì:** nút gợi ý "Ô tô vượt đèn đỏ bị phạt bao nhiêu tiền?". Chờ các bước hiện lần lượt, chữ chạy dần.
- **Nói gì** trong lúc chờ: "Hệ thống đang tìm kiếm lai BM25 + vector, lọc theo ngày, xếp hạng lại, rồi mở rộng trên đồ thị."
- **Bấm gì** khi có câu trả lời:
  1. Rê chuột vào chip trích dẫn `Đ6.K9.b · NĐ 168/2024`: hiện nguyên văn điều khoản.
  2. Bấm chip: bảng bên phải cuộn tới đúng điều khoản.
- **Nói gì:** "*Người dùng nói 'vượt đèn đỏ', văn bản viết 'không chấp hành hiệu lệnh của đèn tín hiệu giao thông'* — hệ thống vẫn tìm đúng."
- **Đáp án đúng:** phạt 18.000.000 – 20.000.000 đồng (điểm b khoản 9 Điều 6 NĐ 168/2024).

### Màn 3. Hội thoại nhiều lượt: D2 (45 giây)

- **Bấm gì:** gõ tiếp vào cùng cuộc trò chuyện: `Còn xe máy thì sao?`
- **Nói gì:** chỉ vào dòng **"Hiểu câu hỏi là: …"**: "*Câu hỏi cụt được viết lại thành câu đầy đủ dựa trên lượt trước* rồi mới tìm kiếm."
- **Đáp án đúng:** xe máy phạt 4.000.000 – 6.000.000 đồng (điểm c khoản 7 Điều 7), trừ 04 điểm (điểm b khoản 13 Điều 7).

### Màn 4. Giá trị của đồ thị: D3 (1,5 phút) — màn quan trọng nhất

- **Bấm gì:** bấm "Cuộc trò chuyện mới", chọn gợi ý "Lái ô tô vượt đèn đỏ có bị trừ điểm giấy phép lái xe không?".
  Khi xong, bấm pill **"… từ đồ thị"** để mở tab **Đồ thị**.
- **Nói gì:** "Câu 'trừ 04 điểm' nằm ở khoản 16, chỉ viết *'thực hiện hành vi quy định tại … điểm b khoản 9 Điều này'*,
  không hề nhắc tới đèn đỏ. Tìm kiếm thông thường khó lấy được khoản này.
  *GraphRAG tìm được điểm b khoản 9, rồi đi ngược cạnh dẫn chiếu trên đồ thị để lấy khoản 16.*"
- Chỉ vào node cam (thêm nhờ đồ thị) nối với node xanh (tìm trực tiếp) bằng cạnh "Dẫn chiếu". Mở tab **Căn cứ**: thẻ có nhãn "Từ đồ thị · Dẫn chiếu với Đ6.K9.b".
- Mở tab **Quy trình**: 6 bước và thời gian từng bước.

### Màn 5. Cùng câu hỏi, ba ngày khác nhau: D4 → D6 (2 phút)

Câu hỏi: **"Chở trẻ em dưới 10 tuổi ngồi ghế trước ô tô bị xử phạt thế nào?"**

| Bước | Bấm gì | Kết quả đúng |
|---|---|---|
| 1 | Cuộc trò chuyện mới. Ô ngày ở góc trên → chọn **01/10/2025**. Gửi câu hỏi | Chưa bị xử phạt theo điểm m: quy định **có hiệu lực từ 01/01/2026** (khung cảnh báo màu vàng) |
| 2 | Đổi ngày → **01/03/2026**, gửi lại đúng câu đó | Phạt 800.000 – 1.000.000 đồng, điểm m khoản 3 Điều 6 bản gốc |
| 3 | Đổi ngày → **01/09/2026**, gửi lại | Vẫn 800.000 – 1.000.000 đồng nhưng theo điểm m **đã được NĐ 238/2026 sửa đổi**; không dùng ghế an toàn cho trẻ chuyển sang khoản 1a mới: phạt cảnh cáo |

- **Nói gì:** "*Mỗi điều khoản được lưu thành nhiều phiên bản theo thời gian.* Hệ thống chỉ đưa cho mô hình phiên bản còn hiệu lực vào ngày người dùng chọn, nên không trả lời bằng luật cũ hoặc luật chưa có hiệu lực."
- **Bấm gì:** trên thẻ điểm m trong bảng Căn cứ, bấm **Lịch sử** → trang Lịch sử sửa đổi hiện dòng thời gian 2 phiên bản, phần bị xóa gạch đỏ, phần thêm tô xanh.

### Màn 6. Hình thức xử phạt bổ sung: D7 (45 giây)

- **Bấm gì:** gợi ý "Lái ô tô mà nồng độ cồn vượt quá 0,4 miligam/1 lít khí thở…".
- **Đáp án đúng:** phạt 30.000.000 – 40.000.000 đồng (điểm a khoản 11 Điều 6) và **tước giấy phép lái xe 22 – 24 tháng** (điểm c khoản 15 Điều 6).
- **Nói gì:** "Phần tước giấy phép lại nằm ở khoản 15, lấy được nhờ cạnh dẫn chiếu, giống màn 4."

### Màn 7 (tùy chọn). Câu nhiều bước: D8

- Chỉ trình bày nếu chạy thử hôm trước ra **ĐẠT**.
- **Đáp án đúng:** tốc độ tối đa 60 km/h (khoản 1 Điều 6 TT 38/2024) → vượt 15 km/h → phạt 4.000.000 – 6.000.000 đồng (điểm đ khoản 5 Điều 6 NĐ 168/2024), trừ 02 điểm.

### Màn 8. Lọc câu hỏi: chào hỏi và ngoài phạm vi: D11, D12, D10 (40 giây)

- **Bấm gì:** cuộc trò chuyện mới, lần lượt gõ `Xin chào`, `Giá vàng hôm nay bao nhiêu?`, `Thủ tục đăng ký kết hôn cần những giấy tờ gì?`
- **Kết quả đúng:**
  - "Xin chào": chào lại, giới thiệu phạm vi, gợi ý câu hỏi; nhãn "Lời chào".
  - Hai câu sau: "Câu hỏi này không thuộc phạm vi hỗ trợ…" kèm gợi ý; nhãn "Ngoài phạm vi hỗ trợ".
- **Nói gì:** "*Trước khi tra cứu, hệ thống phân loại câu hỏi*: câu chào và câu có từ khóa giao thông nhận ra ngay bằng luật,
  câu còn lại mới hỏi LLM. Câu ngoài phạm vi không chạy tìm kiếm, không tốn embedding và không bịa câu trả lời."

### Màn 9. Các trang tra cứu (1,5 phút)

1. **Tra cứu văn bản** → chọn NĐ 168/2024 → đổi "Xem tại" sang **01/09/2026**.
   Các dòng nền cam là phiên bản do văn bản sửa đổi tạo ra (dòng đầu trang đếm số đơn vị đã sửa).
   Rê chuột vào một dòng: nút Hỏi / Lịch sử / Đồ thị.
2. **Khám phá đồ thị** → mặc định mở điểm b khoản 9 Điều 6. Bấm **Đ6.K16.b** ở danh sách Liên kết, bấm **Mở rộng**: hiện các hành vi khác cũng bị trừ 4 điểm.
   Bỏ tích "Thuộc" ở chú thích để chỉ xem cạnh dẫn chiếu.

### Màn 10. Thống kê (30 giây)

- Số văn bản, điều khoản, phiên bản, node, cạnh theo loại; các câu vừa hỏi trong buổi demo; điều khoản được trích dẫn nhiều nhất.
- Trước đó bấm 👍 ở vài câu trả lời để tỉ lệ "hữu ích" có số liệu.

## 3. Bảng câu hỏi và đáp án đúng

| # | Nhóm | Câu hỏi | Ngày áp dụng | Đáp án đúng |
|---|---|---|---|---|
| D1 | Mức phạt | Ô tô vượt đèn đỏ bị phạt bao nhiêu tiền? | hôm nay | 18.000.000 – 20.000.000 đồng (Đ6.K9.b NĐ 168) |
| D2 | Hội thoại | Còn xe máy thì sao? (hỏi tiếp D1) | hôm nay | 4.000.000 – 6.000.000 đồng (Đ7.K7.c), trừ 04 điểm (Đ7.K13.b) |
| D3 | Đồ thị | Lái ô tô vượt đèn đỏ có bị trừ điểm giấy phép lái xe không? | hôm nay | Trừ 04 điểm (Đ6.K16.b → Đ6.K9.b) |
| D4 | Hiệu lực | Chở trẻ em dưới 10 tuổi ngồi ghế trước ô tô bị xử phạt thế nào? | 01/10/2025 | Điểm m chưa có hiệu lực (từ 01/01/2026) |
| D5 | Hiệu lực | (như D4) | 01/03/2026 | 800.000 – 1.000.000 đồng, điểm m bản gốc |
| D6 | Hiệu lực | (như D4) | 01/09/2026 | 800.000 – 1.000.000 đồng, điểm m do NĐ 238 sửa; thiếu ghế an toàn: cảnh cáo (K1a) |
| D7 | Đồ thị | Lái ô tô mà nồng độ cồn vượt quá 0,4 miligam/1 lít khí thở bị xử phạt thế nào? | hôm nay | 30 – 40 triệu đồng (Đ6.K11.a), tước GPLX 22 – 24 tháng (Đ6.K15.c) |
| D8 | Nhiều bước | Ô tô con chạy 75 km/h trên đường đôi trong khu đông dân cư thì bị phạt thế nào? | hôm nay | Tối đa 60 km/h (TT 38 Đ6.K1) → 4 – 6 triệu đồng (Đ6.K5.đ), trừ 02 điểm |
| D9 | Thủ tục | Giấy phép lái xe bị trừ hết điểm thì làm thế nào để được phục hồi? | hôm nay | Sau ít nhất 06 tháng, kiểm tra kiến thức đạt → phục hồi 12 điểm (Luật 36 Đ58.K3) |
| D10 | Ngoài phạm vi | Thủ tục đăng ký kết hôn cần những giấy tờ gì? | hôm nay | "Không thuộc phạm vi hỗ trợ", gợi ý câu hỏi phù hợp |
| D11 | Lời chào | Xin chào | hôm nay | Chào lại, giới thiệu phạm vi, gợi ý câu hỏi |
| D12 | Ngoài phạm vi | Giá vàng hôm nay bao nhiêu? | hôm nay | "Không thuộc phạm vi hỗ trợ" |

Đáp án đã đối chiếu với nội dung trong `data/processed/versions.jsonl`. Nếu thầy hỏi câu ngoài danh sách, cứ gõ thẳng: hệ thống hoạt động với mọi câu, chỉ là chưa chạy thử trước.

## 4. Câu hỏi thầy có thể hỏi

| Câu hỏi | Gợi ý trả lời |
|---|---|
| Khác gì RAG thông thường? | RAG chỉ lấy đoạn giống câu hỏi. GraphRAG lấy thêm điều khoản liên quan qua cạnh dẫn chiếu, cấu trúc (màn 4, 6) và lọc phiên bản theo ngày (màn 5). Phần so sánh định lượng với B1–B3 làm ở tuần sau. |
| Làm sao biết câu trả lời đúng? | Mọi ý đều có trích dẫn bấm được để xem nguyên văn. Bộ câu hỏi đánh giá (~200 câu, có đáp án và mã điều khoản đúng) đang soạn theo hướng dẫn gán nhãn. |
| Mô hình có bịa không? | Câu ngoài phạm vi bị lọc trước khi tra cứu (màn 8); prompt bắt chỉ dùng ngữ cảnh; mã trích dẫn không có trong ngữ cảnh bị đánh dấu đỏ; không có quy định thì trả "không tìm thấy". |
| Luật mới ban hành thì sao? | Thêm .docx + 1 dòng manifest.csv, chạy lại 4 script (01→04, dưới 10 phút). Văn bản sửa đổi được tách tự động thành thao tác sửa đổi và phiên bản mới. |
| Đồ thị dựng thế nào, có dùng LLM không? | Không dùng LLM. Cấu trúc và dẫn chiếu tách bằng regex + máy trạng thái (1.733 dẫn chiếu, 397 thao tác sửa đổi). |
| Vì sao có hai CSDL? | PostgreSQL giữ nội dung, embedding, phiên bản, lọc theo ngày bằng SQL; Neo4j giữ quan hệ để đi theo đồ thị. Hai kho nối bằng mã điều khoản chung. |
| Hạn chế? | Chưa có cạnh HUONG_DAN (NĐ/TT → Luật); 1 câu lệnh sửa đổi phải nhập tay; phụ lục, biểu mẫu chưa đưa vào. |

## 5. Mẹo để demo đẹp mắt

- Giao diện đã có sẵn: chữ chạy dần, các bước pipeline hiện lần lượt, chip trích dẫn rê chuột xem nguyên văn,
  đồ thị con cho từng câu trả lời, so sánh phiên bản tô màu. Hãy **dừng 2–3 giây ở mỗi hiệu ứng** để người xem kịp nhìn.
- Mỗi màn dùng **cuộc trò chuyện mới**, trừ màn 3 (hỏi tiếp). Tên các cuộc trò chuyện ở thanh bên thành mục lục của buổi demo.
- Khi đổi ngày ở màn 5, **nói to ngày đang chọn** và chỉ vào ô ngày ở góc trên.
- Bảng chi tiết bên phải mở rộng khi chọn tab Đồ thị; muốn màn hình rộng cho câu trả lời thì bấm nút ẩn bảng ở góc trên.
- Không cuộn nhanh. Người xem cần thấy chuyển động chậm và rõ.
- Một người thao tác, một người nói; người nói đứng cạnh màn chiếu và chỉ tay vào chỗ đang nói.

## 6. Bật hệ thống bằng tay và xử lý sự cố

```
docker compose -f db/docker-compose.yml --env-file .env up -d        # PostgreSQL + Neo4j
uvicorn backend.app.main:app --port 8000                              # cửa sổ 1 (đã kích hoạt .venv)
cd frontend && npm run dev                                            # cửa sổ 2, mở http://localhost:5173
```

Lần đầu: `pip install -e ".[api]"` trong .venv và `cd frontend && npm install`.

| Hiện tượng | Cách xử lý |
|---|---|
| Góc trái dưới: "Không kết nối được backend" | Cửa sổ uvicorn bị tắt hoặc lỗi: chạy lại lệnh uvicorn, đọc dòng lỗi cuối |
| PostgreSQL hoặc Neo4j chấm đỏ | Docker Desktop chưa bật, hoặc container dừng: chạy lại lệnh docker compose |
| "Không gọi được mô hình qua OpenRouter" | Mất mạng hoặc hết hạn mức: đổi sang mạng điện thoại, kiểm tra trang Credits trên OpenRouter. Không được thì chuyển sang video dự phòng |
| Câu trả lời đầu tiên rất chậm (> 20 giây) | Chưa làm nóng: lần sau hỏi thử 1 câu trước khi vào lớp |
| Bước "Mở rộng trên đồ thị" báo "Neo4j lỗi" | Hệ thống vẫn trả lời (không có phần đồ thị). Khởi động lại container neo4j |
| Câu trả lời sai so với bảng mục 3 | Bấm "Thử lại" (nút ở câu bị lỗi) hoặc chuyển sang câu kế tiếp; ghi lại để sửa sau |
