# Ảnh chụp màn hình cho báo cáo môn Điện toán đám mây

Chụp **ngay lúc làm** (một số màn hình chỉ hiện một lần, ví dụ mật khẩu AuraDB).
Che API key, mật khẩu, chuỗi kết nối trước khi lưu vào đây.

Đặt tên theo bước triển khai để ghép vào mục 2.3 của báo cáo dễ dàng:

| Tiền tố | Bước | Người chụp |
|---|---|---|
| `B1_` | GitHub: repo, cấu trúc thư mục, collaborator | TV1 |
| `B2_` | Supabase: tạo project, bật extension vector, Table Editor, Connect (pooler) | TV2 |
| `B3_` | AuraDB: tạo instance Free, Running, chạy ràng buộc | TV2 |
| `B4_` | Google AI Studio: trang API keys (che key), giới hạn sử dụng | TV1 |
| `B5_` | Nạp dữ liệu: terminal `scripts/04_load.py --env cloud`, bảng don_vi, đồ thị trong Aura | TV2 |
| `B6_` | Render Web Service: cấu hình, Environment, log build, `/health`, `/health/db`, `/docs` | TV1 |
| `B7_` | Render Static Site: cấu hình, log build, trang chủ | TV3 |
| `B8_` | Kiểm thử: giao diện trên điện thoại, tab Events (tự deploy khi push), GitHub Actions xanh | Cả nhóm |
| `B9_` | Giám sát: Render Metrics/Logs, Supabase Usage, trang Billing 0 USD | TV3 |

Ví dụ: `B6_03_render_environment.png`, `B2_02_supabase_extension_vector.png`.
