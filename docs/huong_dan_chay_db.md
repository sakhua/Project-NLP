# Chạy, sử dụng và theo dõi cơ sở dữ liệu

Áp dụng cho máy của nhóm (môi trường `local`, Windows). Bản cloud (Supabase + AuraDB) dùng cùng các script, thêm `--env cloud`.
Thiết kế dữ liệu: `docs/thiet_ke_do_thi.md`.

## 1. Chuẩn bị (một lần)

1. Cài **Docker Desktop** (bật WSL2 khi được hỏi), mở Docker Desktop và chờ biểu tượng chuyển sang "Running".
2. Trong thư mục dự án, đã có venv và `pip install -r requirements.txt` (xem `CLAUDE.md`).
3. `copy .env.example .env`, điền `OPENROUTER_API_KEY`. Mật khẩu DB để mặc định cũng được (Neo4j yêu cầu ≥ 8 ký tự).

## 2. Bật PostgreSQL và Neo4j

```powershell
docker compose -f db/docker-compose.yml --env-file .env up -d
docker ps                      # phải thấy graphrag_postgres và graphrag_neo4j ở trạng thái Up
```

| Dịch vụ | Địa chỉ | Tài khoản (mặc định trong .env) |
|---|---|---|
| PostgreSQL | `localhost:5432`, database `luat_gt` | `graphrag` / `doi_mat_khau` |
| Neo4j Browser | http://localhost:7474 | `neo4j` / `doi_mat_khau` |
| Neo4j (cho code) | `bolt://localhost:7687` | như trên |

Dữ liệu của hai DB nằm trong `db/volumes/` (đã có trong `.gitignore`), tắt máy không mất.
Tắt: `docker compose -f db/docker-compose.yml down`. Xóa sạch để làm lại từ đầu: tắt rồi xóa thư mục `db/volumes`.

## 3. Nạp dữ liệu (chạy lại mỗi khi dữ liệu đổi)

```powershell
python scripts/02_extract_relations.py   # sửa đổi → phiên bản → dẫn chiếu        (vài giây)
python scripts/03_embed.py               # embedding mọi phiên bản qua OpenRouter (1–3 phút, < 0,01 USD)
python scripts/04_load.py                # nạp PostgreSQL + Neo4j                  (khoảng 30 giây)
```

Kết quả mong đợi (số liệu ngày 21/10/2026):

- Bước 2: `397 thao tác sửa đổi, 3356 phiên bản, 1733 dẫn chiếu`. Chi tiết và cảnh báo: `data/processed/versions_report.md`.
- Bước 4 in bảng số phiên bản, số đơn vị, số đã hết hiệu lực, số có embedding theo từng văn bản; số node, số cạnh
  Neo4j theo loại; và dòng `mọi mã trong Neo4j đều có trong PostgreSQL`. **Chụp màn hình bảng này** cho báo cáo.

Tùy chọn của `04_load.py`:

| Lệnh | Khi nào dùng |
|---|---|
| `--chi postgres` / `--chi neo4j` | chỉ nạp một DB (ví dụ chưa bật Neo4j) |
| `--tao-lai-bang` | báo lỗi "lược đồ cũ (chưa có cột vid)": DB tạo trước ngày 21/10, bảng `don_vi` cần tạo lại |
| `--env cloud` | nạp lên Supabase + AuraDB (đọc `.env.cloud`) |

Mỗi lần chạy, `04_load.py` xóa dữ liệu văn bản cũ rồi nạp lại toàn bộ, nên chạy lại thoải mái; bảng nhật ký hỏi đáp giữ nguyên.
Chưa chạy bước 3 thì bước 4 vẫn nạp được, chỉ thiếu cột embedding (in ra nhắc chạy bước 3).

## 4. Sử dụng

### 4.1. Xem PostgreSQL

Cách dễ nhất: cài **DBeaver Community** (miễn phí) → New Connection → PostgreSQL → điền thông tin ở mục 2.
Hoặc dòng lệnh: `docker exec -it graphrag_postgres psql -U graphrag -d luat_gt`.

```sql
-- Số phiên bản theo văn bản
SELECT van_ban_id, count(*) AS phien_ban, count(DISTINCT id) AS don_vi FROM don_vi GROUP BY 1 ORDER BY 1;

-- Lịch sử một điều khoản (mọi phiên bản)
SELECT vid, hieu_luc_tu, hieu_luc_den, loai_phien_ban, nguon_sua_doi, left(noi_dung, 80)
FROM don_vi WHERE id = 'ND168_2024.D6.K3.m' ORDER BY hieu_luc_tu;

-- Nội dung có hiệu lực tại một ngày (đúng điều kiện pipeline dùng)
SELECT vid, noi_dung FROM don_vi
WHERE id LIKE 'ND168_2024.D6.K3%' AND hieu_luc_tu <= '2026-09-01'
  AND (hieu_luc_den IS NULL OR '2026-09-01' < hieu_luc_den) ORDER BY thu_tu;

-- Những gì thay đổi khi NĐ 238 có hiệu lực (15/08/2026)
SELECT id, loai_phien_ban, nguon_sua_doi FROM don_vi WHERE hieu_luc_tu = '2026-08-15' ORDER BY thu_tu;

-- Điều khoản có nội dung gần nhất với một điều khoản (kiểm tra embedding)
SELECT vid, left(noi_dung, 80), embedding <=> (SELECT embedding FROM don_vi WHERE vid = 'ND168_2024.D6.K9.b@2025-01-01') AS kc
FROM don_vi WHERE embedding IS NOT NULL ORDER BY kc LIMIT 5;
```

### 4.2. Xem đồ thị trong Neo4j Browser

Mở http://localhost:7474, đăng nhập, gõ câu lệnh vào ô trên cùng rồi Ctrl+Enter.
Bấm vào tên nhãn (ví dụ `Diem`) ở khung kết quả → Caption → chọn `id` để node hiện mã.

```cypher
// Các văn bản và quan hệ sửa đổi giữa văn bản
MATCH (v:VanBan) OPTIONAL MATCH p = (v)-[:SUA_DOI]->(:VanBan) RETURN v, p

// Cây Điều 6 NĐ 168 (khoản, điểm)
MATCH p = (:DonVi)-[:THUOC*1..2]->(:Dieu {id: 'ND168_2024.D6'}) RETURN p LIMIT 150

// Dẫn chiếu quanh điểm "vượt đèn đỏ" (thấy khoản trừ điểm trỏ vào)
MATCH p = (:DonVi {id: 'ND168_2024.D6.K9.b'})-[:THAM_CHIEU]-(:DonVi) RETURN p

// NĐ 238 sửa những gì trong Điều 6
MATCH p = (a:DonVi)-[r:SUA_DOI|THAY_THE|BO_SUNG|BAI_BO]->(b:DonVi)
WHERE b.id STARTS WITH 'ND168_2024.D6.' RETURN p

// 10 điều khoản được dẫn chiếu nhiều nhất
MATCH (n:DonVi)<-[:THAM_CHIEU]-() RETURN n.id, count(*) AS so_lan ORDER BY so_lan DESC LIMIT 10
```

### 4.3. Qua API của dự án

```powershell
uvicorn backend.app.main:app --reload
```

Mở http://localhost:8000/docs và bấm "Try it out":

| API | Thử với |
|---|---|
| `GET /health/db` | kiểm tra kết nối hai DB, số đơn vị, số node |
| `GET /api/documents` | danh sách 12 văn bản |
| `GET /api/documents/ND168_2024/units?date=2026-09-01` | các điều khoản NĐ 168 có hiệu lực tại ngày đó |
| `GET /api/units/ND168_2024.D6.K3.m` | mọi phiên bản + văn bản đã sửa đổi điểm này |
| `GET /api/graph/ND168_2024.D6.K9.b` | đồ thị 1 bước quanh một điều khoản |
| `POST /api/ask` | trả 501 cho tới khi `graph_rag.answer` xong (tuần 5–6) |

### 4.4. Trong code Python

```python
from datetime import date
from graphrag.common.config import load_config
from graphrag.resources import Resources
from graphrag.storage import postgres, neo4j_store

res = Resources(load_config("local"))
with res.pg_pool.connection() as conn:
    print(postgres.fetch_valid(conn, ["ND168_2024.D6.K3.m"], date(2026, 9, 1)))
print(neo4j_store.expand(res.neo4j, ["ND168_2024.D6.K9.b"], hops=1))
print(res.bm25.search("vượt đèn đỏ ô tô", k=5))          # trả về vid
```

## 5. Theo dõi

| Muốn biết | Cách xem |
|---|---|
| Container còn chạy, tốn bao nhiêu RAM/CPU | `docker ps`, `docker stats` (hoặc tab Containers của Docker Desktop) |
| Lỗi của DB | `docker compose -f db/docker-compose.yml logs -f postgres` (hoặc `neo4j`) |
| Ứng dụng kết nối được DB không | `GET /health/db` |
| Dung lượng PostgreSQL | `SELECT pg_size_pretty(pg_database_size('luat_gt'));` (Supabase Free giới hạn 500 MB; hiện khoảng 50 MB) |
| Số kết nối đang mở | `SELECT count(*) FROM pg_stat_activity WHERE datname = 'luat_gt';` |
| Neo4j: dung lượng, bộ nhớ | gõ `:sysinfo` trong Neo4j Browser |
| Số node, cạnh | `MATCH (n) RETURN count(n)`; `MATCH ()-[r]->() RETURN type(r), count(*)` (AuraDB Free: 50.000 node, 175.000 cạnh; hiện khoảng 3.100 node) |
| Chất lượng dữ liệu | `corpus_report.md`, `versions_report.md`, `python scripts/kiem_tra_corpus.py` |
| Nhật ký hỏi đáp, đánh giá của người dùng | bảng `hoi_dap_log`; `GET /api/admin/stats` (cần `X-Admin-Password`) |

Trên cloud: Supabase → Table Editor / Reports / Database → Usage; Aura console → instance → Metrics.

## 6. Lỗi thường gặp

| Thông báo | Cách xử lý |
|---|---|
| `port is already allocated` (5432 hoặc 7474) | Máy đã có PostgreSQL/Neo4j khác: tắt dịch vụ đó, hoặc đổi cổng bên trái trong `db/docker-compose.yml` (vd. `"5433:5432"`) và `POSTGRES_PORT` trong `.env` |
| `connection refused` | Docker Desktop chưa chạy hoặc container chưa lên; `docker ps` |
| `password authentication failed` | `.env` đổi mật khẩu sau khi DB đã tạo: mật khẩu cũ vẫn được dùng. Sửa lại `.env` hoặc xóa `db/volumes` rồi bật lại |
| `Bảng don_vi đang theo lược đồ cũ` | `python scripts/04_load.py --tao-lai-bang` |
| Neo4j `Unauthorized` lần đầu | mật khẩu trong `.env` phải giống `NEO4J_AUTH` lúc tạo container; xóa `db/volumes/neo4j` rồi bật lại |
| `X phiên bản chưa có embedding` | chạy lại `scripts/03_embed.py` sau mỗi lần chạy bước 2 |

## 7. Kiểm tra tay sau mỗi lần dữ liệu đổi (TV2)

- `versions_report.md`: đọc mục "Cảnh báo cần kiểm tra tay". Hiện còn 1 câu lệnh phải nhập tay:
  NĐ 238 khoản 2 Điều 17 sửa "đoạn thứ hai điểm a khoản 3 Điều 50" → thêm vào `amendments.jsonl` một thao tác
  `cum_tu` rồi chạy `02_extract_relations.py --dung-amendments-co-san`.
- Chọn ngẫu nhiên 30 dòng trong `amendments.jsonl` và 50 dòng trong `references.jsonl`, đối chiếu với văn bản.
- So vài điều khoản của Luật 36 sau sửa đổi (`hieu_luc_tu = 2026-07-01`) với văn bản hợp nhất VBHN 55.
