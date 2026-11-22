# GraphRAG – Hỏi đáp pháp luật giao thông đường bộ Việt Nam

Đề tài: **Xây dựng hệ thống hỏi đáp pháp luật giao thông đường bộ Việt Nam dựa trên GraphRAG** (nhóm 3 thành viên).

Một mã nguồn phục vụ hai môn:

| Môn | Phần chính trong repo | Môi trường chạy |
|---|---|---|
| Xử lý ngôn ngữ tự nhiên | `graphrag/` (pipeline, đánh giá), `scripts/`, `notebooks/` | `local`: máy nhóm, bge-m3 + reranker, PostgreSQL/Neo4j trong Docker |
| Điện toán đám mây | `backend/`, `frontend/`, `render.yaml`, `.github/` | `cloud`: Render + Supabase + Neo4j AuraDB |

Thiết kế chi tiết: `kien_truc_he_thong.html`, `bai_toan.html`, `Cloud/ke_hoach_trien_khai_cloud.html` ở thư mục báo cáo.

## Kiến trúc tóm tắt

- **PostgreSQL + pgvector**: nội dung từng Điều/Khoản/Điểm, embedding, thời điểm hiệu lực (nguồn dữ liệu gốc).
- **Neo4j**: chỉ lưu mã định danh và quan hệ (THUOC, THAM_CHIEU, HUONG_DAN, SUA_DOI, BO_SUNG, THAY_THE, BAI_BO, CHUYEN_TIEP).
- Hai kho nối với nhau qua **mã định danh chung**, ví dụ `ND168_2024.D6.K5.a` (`graphrag/common/ids.py`).

Luồng trả lời: (1) BM25 + vector, gộp RRF, rerank → (2) Neo4j mở rộng quan hệ và chuỗi sửa đổi →
(3) PostgreSQL lọc theo ngày áp dụng → (4) LLM sinh câu trả lời có trích dẫn.

### Mô hình (gọi qua OpenRouter, dùng chung cho cả hai môi trường)

| Vai trò | Mô hình mặc định (`configs/base.yaml`) | Thay thế |
|---|---|---|
| Embedding | `baai/bge-m3` (1024 chiều, cột `don_vi.embedding`) | chạy bge-m3 trên máy: `embedding.provider: local` |
| Rerank | `cohere/rerank-v3.5` | `cohere/rerank-4-fast`, `qwen/qwen3-reranker-4b`, `voyageai/rerank-2.5` |
| Sinh câu trả lời, dựng chỉ mục B2 | `openai/gpt-6-luna` | bất kỳ mô hình chat nào trên OpenAI/OpenRouter (thử bằng `scripts/thu_mo_hinh.py`) |
| LLM-judge (đánh giá) | `openai/gpt-4o` | nên mạnh hơn mô hình sinh câu trả lời |

Một khóa `OPENROUTER_API_KEY` cho cả ba loại; nên đặt hạn mức chi tiêu (credit limit) cho khóa.
Vì không chạy mô hình trên máy chủ, bản cloud (Render 512 MB) chạy **đúng pipeline** như bản đánh giá.

### Khác biệt giữa hai môi trường

| | `local` (môn NLP) | `cloud` (môn Điện toán đám mây) |
|---|---|---|
| PostgreSQL / Neo4j | Docker (`db/docker-compose.yml`) | Supabase / AuraDB Free |
| Cấu hình | `configs/local.yaml` + `.env` | `configs/cloud.yaml` + `.env.cloud` hoặc biến môi trường Render |
| Mô hình | giống nhau (OpenRouter) | giống nhau; giới hạn `max_tokens` 800 |

Chọn môi trường bằng biến `APP_ENV` (mặc định `local`). Corpus được tính embedding một lần trên máy nhóm
(`scripts/03_embed.py`) rồi nạp vào DB của từng môi trường.

## Cấu trúc thư mục

```
graphrag-luat-giao-thong/
├── graphrag/                  # LÕI DÙNG CHUNG (gói Python, trước đây là src/)
│   ├── common/                #   config.py (đọc base + local/cloud), ids.py
│   ├── parsing/               #   đọc docx, tách cấu trúc, dẫn chiếu, sửa đổi        (TV2)
│   ├── embedding/             #   openrouter.py (mặc định), local_bge_m3.py, get_embedder (TV3)
│   ├── retrieval/             #   bm25.py, fusion.py (RRF), rerank.py                (TV3)
│   ├── storage/               #   postgres.py, neo4j_store.py                        (TV2, TV1)
│   ├── llm/                   #   gọi LLM sinh câu trả lời / LLM-judge                (TV1)
│   ├── pipeline/              #   baseline_rag.py, graph_rag.py, prompts.py          (TV3, TV1)
│   ├── evaluation/            #   độ đo, LLM-judge, run_eval.py                      (TV3)
│   ├── openrouter.py          #   client OpenRouter: chat, embeddings, rerank
│   └── resources.py           #   gom kết nối DB, mô hình, chỉ mục BM25 dùng chung
├── backend/                   # CLOUD – API FastAPI, chạy trên Render Web Service     (TV1)
│   ├── Dockerfile             #   build từ thư mục gốc: docker build -f backend/Dockerfile .
│   └── app/
│       ├── main.py            #   tạo app, CORS, /health, /health/db
│       ├── deps.py, schemas.py
│       └── routers/           #   ask (F1), documents (F2), graph (F3), feedback (F4), admin (F5)
├── frontend/                  # CLOUD – React + Vite, chạy trên Render Static Site     (TV3)
│   └── src/                   #   App.jsx, api.js, pages/ (Hỏi đáp, Tra cứu, Đồ thị, Quản trị)
├── scripts/                   # Chạy OFFLINE trên máy nhóm, theo thứ tự
│   ├── 00_check_manifest.py   #   kiểm tra manifest.csv (ô trống, định dạng ngày…)   (TV2)
│   ├── 01_parse.py            #   docx → corpus.jsonl + corpus_report.md              (TV2)
│   ├── 02_extract_relations.py#   → references.jsonl, amendments.jsonl               (TV2)
│   ├── 03_embed.py            #   → embedding.npy (bge-m3 qua OpenRouter)             (TV3)
│   ├── 04_load.py             #   nạp vào DB local hoặc Supabase/AuraDB (--env cloud) (TV2)
│   └── streamlit_demo.py      #   giao diện thử nhanh cho môn NLP
├── configs/                   # base.yaml + local.yaml + cloud.yaml
├── db/                        # schema.sql, neo4j_constraints.cypher, docker-compose.yml (DB local)
├── data/                      # manifest.csv, raw/ (.docx), reference/, processed/, eval/
├── docs/anh-trien-khai/       # ảnh chụp màn hình các bước triển khai (báo cáo Cloud)
├── notebooks/                 # thống kê dữ liệu, biểu đồ kết quả
├── tests/                     # pytest: ids, metrics, API, cấu hình
├── .github/workflows/ci.yml   # GitHub Actions: chạy test + build frontend mỗi lần push
├── render.yaml                # Render Blueprint (tùy chọn, tạo nhanh 2 dịch vụ)
├── pyproject.toml             # gói graphrag + nhóm thư viện: api, ml, parse, eval, demo, dev
├── requirements.txt           # cài cho máy nhóm (không gồm torch)
├── .env.example               # mẫu biến môi trường local
└── .env.cloud.example         # mẫu biến môi trường cloud
```

## Cài đặt trên máy (môn NLP)

```bash
python -m venv .venv
.venv\Scripts\activate                      # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env                      # điền khóa API, mật khẩu DB

docker compose -f db/docker-compose.yml --env-file .env up -d     # PostgreSQL + Neo4j
python -m pytest -q                         # kiểm tra nhanh
```

Xử lý dữ liệu: `python scripts/01_parse.py` → `02_extract_relations.py` → `03_embed.py` → `04_load.py`.
Đánh giá: `python -m graphrag.evaluation.run_eval --systems B1 B2 B3 GRAPH`.

## Chạy bản web trên máy

```bash
uvicorn backend.app.main:app --reload       # API: http://localhost:8000/docs
cd frontend && copy .env.example .env.local && npm install && npm run dev   # http://localhost:5173
```

## Triển khai lên cloud (môn Điện toán đám mây)

1. Supabase: tạo project (Singapore), bật extension `vector`, chạy `db/schema.sql` trong SQL Editor.
2. AuraDB Free: tạo instance, lưu file credentials, chạy `db/neo4j_constraints.cypher`.
3. Máy nhóm: `copy .env.cloud.example .env.cloud`, điền giá trị, rồi `python scripts/04_load.py --env cloud`
   (dùng lại `embedding.npy` đã tính ở bước 3, không cần tính lại).
4. Render → New → **Web Service**: chọn repo, Language **Docker**, Root Directory để trống,
   Dockerfile Path `./backend/Dockerfile`, Docker Build Context `.`, Instance **Free**, Health Check Path `/health`;
   khai báo các biến trong `.env.cloud.example` ở mục Environment. Kiểm tra `/health` và `/health/db`.
5. Render → New → **Static Site**: Root Directory `frontend`, Build Command `npm ci && npm run build`,
   Publish Directory `dist`, biến `VITE_API_URL` = địa chỉ Web Service; thêm Rewrite `/*` → `/index.html`.
6. Đặt `CORS_ORIGINS` của Web Service = địa chỉ Static Site, deploy lại.

Hoặc tạo cả hai dịch vụ một lần bằng `render.yaml` (Render → New → Blueprint).

Thử image backend giống trên Render ngay trên máy:
`docker compose -f db/docker-compose.yml --profile api up -d --build` (cần file `.env.cloud`).

## Quy ước

- Mã định danh: `<MaVanBan>.D<số điều>.K<số khoản>.<điểm>`; ví dụ `L36_2024.D10`, `ND168_2024.D6.K5.a`.
- Mỗi người làm trên nhánh riêng, merge qua Pull Request, nhóm trưởng review; `main` luôn deploy được.
- Không commit `.env`, `.env.cloud`, API key, mật khẩu. Lỡ lộ thì thu hồi key và đổi mật khẩu ngay.
- Kết quả gọi LLM luôn được cache trong `data/processed/cache/` để không gọi lại khi sửa độ đo.
