# Review parser v1 (TV1, 21/10/2026)

Đối tượng: `graphrag/parsing/structure_parser.py`, `docx_reader.py` và đầu ra `data/processed/corpus.jsonl` (2.997 đơn vị).
Công cụ kiểm tra mới: `python scripts/kiem_tra_corpus.py` (chạy lại sau mỗi lần sửa parser).

## Kết luận

Parser v1 dùng được cho tuần 4–5. Cấu trúc 11 văn bản đúng; chỉ có **2 lỗi cần sửa** (mục 2.1, 2.2), cả hai đều nhỏ và
ảnh hưởng tới mã định danh, nên phải sửa **trước khi** cả nhóm soạn thêm câu hỏi (mã gold sẽ đổi).

## 1. Những gì đã đúng

| Kiểm tra | Kết quả |
|---|---|
| Số Điều so với văn bản gốc | Khớp (L36: 89, NĐ 168: 55, NĐ 151: 39…) |
| Mã trùng, đơn vị mất cha, nội dung rỗng | 0 |
| Đơn vị quá dài (có thể sót ranh giới khoản/điểm), tiêu đề "Điều N." lọt vào nội dung | 0 |
| Khoản đánh số liên tục 1, 2, 3… (cho phép khoản chèn 1a, 9a) | Đúng ở mọi Điều |
| Dẫn chiếu nội bộ "điểm x khoản y Điều này / Điều z" trong 5 văn bản gốc | 572 dẫn chiếu, giải được 568 (99,3%) |
| Dừng đúng trước bảng chữ ký, "Nơi nhận", phụ lục | Đúng ở cả 11 văn bản |

3 trong 4 dẫn chiếu không giải được là dẫn chiếu sang **Luật** mà câu không ghi tên văn bản ngay sau
(`ND151_2024.D1.K5`, `D1.K6`, `D38.K2.c`), không phải lỗi parser. Dẫn chiếu còn lại là lỗi ở mục 2.1.

## 2. Lỗi cần sửa (TV2)

### 2.1. Quy tắc đặt lại chữ điểm khi văn bản đánh sai

Văn bản Word tải về có lỗi đánh máy chữ điểm ở 3 chỗ trong NĐ 168:

| Khoản | Văn bản ghi | Parser v1 đặt | Nên đặt |
|---|---|---|---|
| `ND168_2024.D16.K2` | a b c **đ đ** | a b c đ **e** | a b c **d** đ |
| `ND168_2024.D40.K3` | a b c **đ đ c** | a b c đ **e g** | a b c **d đ e** |
| `ND168_2024.D39.K9` | a b c **đ** | a b c đ | a b c **d** (cần đối chiếu) |

Bằng chứng cho cột "Nên đặt": trong cùng Điều 16, khoản 4 viết "điểm **d** khoản 2 … bị tịch thu biển số" (đúng hành vi
"gắn biển số không đúng" là chữ đ thứ nhất) và "điểm c, điểm **đ** khoản 2" (đúng hành vi "sử dụng chứng nhận đăng ký"
là chữ đ thứ hai). Parser v1 làm dẫn chiếu `ND168_2024.D16.K4.a → D16.K2.d` trỏ vào mã không tồn tại.

**Sửa:** khi chữ điểm khác chữ dự kiến theo thứ tự `a b c d đ e g h i k l m n o p q r s t u v x y`, luôn đặt theo
**chữ dự kiến** và giữ chữ gốc trong `so_goc` (hiện chỉ làm khi chữ bị lặp). Sau đó đối chiếu 3 khoản trên với vbpl.vn
và ghi kết quả vào `corpus_report.md`.

### 2.2. Nội dung sửa đổi không có ngoặc kép (`ND238_2026.D8.K3`)

Văn bản ghi "Sửa đổi, bổ sung điểm c khoản 5 như sau:" rồi xuống dòng "c) Điều khiển xe …" **không có ngoặc kép**.
Parser v1 hiểu "c)" là điểm c của chính NĐ 238 (`ND238_2026.D8.K3.c`), trong khi đây là nội dung mới của
điểm c khoản 5 Điều 21 NĐ 168.

**Sửa:** trong văn bản `vai_tro = sua_doi`, nếu một khoản kết thúc bằng "như sau:" và đoạn tiếp theo không mở ngoặc kép,
coi các đoạn tiếp theo là khối trích dẫn (`co_trich_dan = true`) cho tới khoản kế tiếp của văn bản sửa đổi. Rà toàn bộ
corpus chỉ có đúng 1 chỗ này (lệnh kiểm tra trong `kiem_tra_corpus.py` có thể bổ sung sau).

## 3. Lưu ý, không phải lỗi

- **Khối trích dẫn được giữ nguyên một đơn vị** (ví dụ `ND238_2026.D13` chứa toàn văn Điều 42 mới). Đây là thiết kế:
  bước sửa đổi (`amendment_parser`, tuần 4–5) sẽ tách khối này thành các Khoản/Điểm của văn bản bị sửa,
  xem `docs/thiet_ke_do_thi.md` mục 4.
- Số đơn vị của văn bản sửa đổi vì vậy nhỏ hơn số Khoản/Điểm thực sự được sửa; không so sánh với văn bản gốc.
- Văn bản sửa đổi tạo ra **mã mới**: khoản chèn `ND168_2024.D6.K1a`, điểm chèn `ND168_2024.D41.K4.k1`. Mã điểm dạng
  `k1` trước đây không hợp lệ; đã sửa `graphrag/common/ids.py` để chấp nhận.
- NĐ 184: ngoặc kép không đóng trước "Điều 22" nằm ngoài phạm vi lấy (chỉ lấy Điều 27, 28), không ảnh hưởng.
- `ngu_canh` của điểm có câu dẫn của khoản ("Phạt tiền từ … đối với …"), đúng mục đích tìm kiếm.

## 4. Việc tiếp theo

| Việc | Người | Hạn |
|---|---|---|
| Sửa 2.1, 2.2; chạy lại `01_parse.py` và `kiem_tra_corpus.py` (mục tiêu: chỉ còn 3 dẫn chiếu sang Luật) | TV2 | T4 28/10 |
| Đối chiếu 3 khoản ở 2.1 trên vbpl.vn | TV2 | T4 28/10 |
| Kiểm tra câu hỏi nào đã dùng `D16.K2.e`, `D40.K3.e`, `D40.K3.g` làm gold và sửa theo mã mới | cả nhóm | sau khi sửa |
