# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Hướng dẫn cho Claude Code (VS Code) và cho thành viên mới đọc để hiểu nhanh dự án.
Đọc file này trước khi sửa code. Chi tiết hơn: `README.md`, `docs/thiet_ke_do_thi.md` (đồ thị, phiên bản hiệu lực), `docs/huong_dan_gan_nhan.md`.

## Dự án

**Hệ thống hỏi đáp pháp luật giao thông đường bộ Việt Nam dựa trên GraphRAG.** Nhóm 3 người: TV1 là nhóm trưởng, cùng TV2 và TV3.

Cùng một mã nguồn phục vụ hai môn:

- **Xử lý ngôn ngữ tự nhiên** (môi trường `local`): xây pipeline, so sánh hệ thống đề xuất **Hybrid GraphRAG** với hai baseline
  **B1 Hybrid RAG** (BM25 + vector + rerank, không đồ thị) và **B2 GraphRAG kiểu Microsoft** (đồ thị thực thể do LLM trích,
  cộng đồng Leiden, local/global search; cài đặt lại theo Edge và cộng sự, 2024) trên bộ câu hỏi tự soạn (quyết định 05/11, thay B1–B3 cũ).
- **Điện toán đám mây** (môi trường `cloud`): đưa đúng pipeline đó lên Render, Supabase và Neo4j AuraDB thành web công khai (xem mục "Môn Điện toán đám mây").

Người dùng hỏi bằng tiếng Việt và có thể chọn **ngày áp dụng**. Hệ thống trả lời kèm trích dẫn Điều/Khoản/Điểm **còn hiệu lực tại ngày đó**. Đây là điểm khác biệt chính của đề tài.

- Kho dữ liệu: `data/manifest.csv` có 12 dòng, gồm 11 văn bản pháp luật (file .docx trong `data/raw/`) và 1 văn bản hợp nhất (VBHN 55, file PDF trong `data/reference/`) chỉ dùng để đối chiếu.
- 11 văn bản pháp luật được tách thành 2.997 đơn vị (`data/processed/corpus.jsonl`).
- Các mốc: dữ liệu chốt ngày 25/10/2026, báo cáo giữa kỳ 15/11, code GraphRAG chốt ngày 22/11, nộp bài 06/12/2026.
- **Thứ tự ưu tiên hiện tại (quyết định 24/10):** làm xong hệ thống chạy được từ đầu đến cuối (DB → B1–B3 → GraphRAG) trước,
  **sau đó mới soạn bộ câu hỏi đánh giá**. Hiện chỉ có 5 câu mẫu trong `data/eval/questions_template.jsonl`; dùng chúng để thử pipeline.

## Lệnh thường dùng

Chạy mọi lệnh từ thư mục gốc repo, sau khi activate venv. Dùng Python 3.11, khớp với Dockerfile.

```bash
py -3.11 -m venv .venv && .venv\Scripts\activate      # Windows; Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt                       # = pip install -e .[api,parse,eval,demo,dev], KHÔNG có torch
pip install -e ".[ml]"                                # chỉ khi muốn chạy bge-m3 / reranker trên máy có GPU (kéo torch)
copy .env.example .env                                # điền OPENROUTER_API_KEY, mật khẩu DB

python -m pytest -q                                   # chạy test, phải qua hết trước khi mở PR
python -m pytest tests/test_ids.py -q                 # một file test
python -m pytest tests/test_ids.py -k parse -q        # một test theo tên (không có linter/formatter cấu hình trong repo)
docker compose -f db/docker-compose.yml --env-file .env up -d   # PostgreSQL + Neo4j trên máy

# Pipeline dữ liệu, chạy theo thứ tự
python scripts/00_check_manifest.py
python scripts/01_parse.py              # docx -> corpus.jsonl + corpus_report.md
python scripts/kiem_tra_corpus.py       # kiểm tra đánh số, dẫn chiếu nội bộ sau mỗi lần sửa parser
python scripts/02_extract_relations.py  # -> amendments.jsonl, versions.jsonl, references.jsonl, versions_report.md
python scripts/03_embed.py              # -> embedding.npy cho mọi phiên bản (bge-m3 qua OpenRouter, < 0,01 USD)
python scripts/04_load.py [--env cloud] # nạp vào PostgreSQL + Neo4j (xóa dữ liệu văn bản cũ rồi nạp lại)
python scripts/05_ms_graphrag_index.py [--gioi-han 100] [--uoc-tinh] [--chi-nap --env cloud]   # chỉ mục baseline B2 (gọi LLM, có lưu đệm; cần ".[msgraph]")

# Tra cứu và kiểm tra câu hỏi
python scripts/tim_dieu_khoan.py vượt đèn đỏ --van-ban ND168_2024
python scripts/tim_dieu_khoan.py --ma ND168_2024.D6.K9
python scripts/check_questions.py data/eval/questions_TV1.jsonl
python scripts/thu_prompt.py           # thử prompt sinh câu trả lời với ngữ cảnh chuẩn (cần OPENROUTER_API_KEY)

# Đánh giá: 3 hệ thống (GRAPH = đề xuất, B1 = Hybrid RAG, B2 = GraphRAG kiểu Microsoft), CHỈ dùng 6 độ đo không LLM:
# Recall@k, Full Recall@k, MRR@k, F2@k, Faithfulness, Answer Relevance (graphrag/evaluation/metrics.py) + paired bootstrap
python -m graphrag.evaluation.run_eval --systems GRAPH B1 B2 --questions data/eval/bo_test_tu_dong.jsonl
python scripts/chay_bo_test.py --he-thong hybrid_graphrag hybrid_rag ms_graphrag [--gioi-han 20]
# Bộ test tự động 200 câu (sinh từ versions.jsonl, KHÔNG phải bộ chính thức) + chạy GraphRAG thật và chấm
python scripts/sinh_bo_test.py                        # → data/eval/bo_test_tu_dong.jsonl (không ghi đè file đã rà soát)
streamlit run scripts/ra_soat_app.py                  # giao diện rà soát/sửa bộ câu golden, bấm Lưu ghi thẳng vào JSONL
python scripts/chay_bo_test.py [--gioi-han 20] [--tiep]   # → data/eval/ket_qua/bao_cao_*.md/.csv
python scripts/chay_bo_test.py --cham-lai <ket_qua_*.jsonl>   # chấm lại file kết quả, không gọi API

# Web trên máy (demo): một lệnh bật Docker + backend + frontend, hoặc làm tay 2 dòng dưới
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1        # bản build, không tự tải lại trang; thêm -Dev khi sửa giao diện
uvicorn backend.app.main:app --reload                 # http://localhost:8000/docs (cần pip install -e ".[api]")
cd frontend && npm install && npm run dev             # http://localhost:5173 (npm run build để build; frontend chưa có test/lint)
python scripts/kiem_tra_demo.py                       # chạy thử 10 câu demo (data/demo/cau_hoi_demo.json), kịch bản: docs/kich_ban_demo.md
streamlit run scripts/streamlit_demo.py               # demo nhanh không cần frontend (extras `demo`)
```

Nếu sửa schema (`db/schema.sql`, `db/neo4j_constraints.cypher`) thì `04_load.py` là bước áp dụng; các script 00–04 đọc/ghi file trong `data/processed/` nên chạy lại theo thứ tự khi đổi parser hoặc manifest.

## Kiến trúc

**Ba hệ thống, một giao diện gọi:** `graphrag/pipeline/he_thong.py::run/answer(res, question, he_thong=..., ngay, history, che_do)`.
Backend (`he_thong`, `che_do` trong body của `/api/ask(/stream)`, danh sách ở `GET /api/systems`), giao diện (nút chọn + chế độ So sánh
ba cột) và script đánh giá đều đi qua đây. Cả ba dùng chung `tien_xu_ly` (phân loại, viết lại câu hỏi), prompt, cách trích dẫn, lọc ngày.

| `he_thong` | Mã log | Module | Truy hồi |
|---|---|---|---|
| `hybrid_graphrag` (mặc định) | GRAPH | `pipeline/graph_rag.py` | các bước 0–4 dưới đây |
| `hybrid_rag` | B1 | `pipeline/baseline_rag.py` | = `graph_rag.run(hops=0)`: bỏ bước mở rộng đồ thị |
| `ms_graphrag` | B2 | `ms_graphrag.ban: goc` (mặc định) → `pipeline/ms_graphrag_goc.py`; `luat` → `pipeline/ms_graphrag.py` | goc: local search gốc của Microsoft (20 thực thể, ngân sách 12.000 token: Reports 15%, Sources 50%), prompt gốc, KHÔNG lọc theo ngày, trích dẫn `[Data: Sources (id)]` đổi về mã điều khoản; luat: bản đã chỉnh cho luật (tạm không dùng) |

Chỉ mục B2 bản gốc (từ 22/11): `scripts/05_ms_graphrag_index.py --ban goc` + `ms_graphrag/indexing_goc.py`, `prompts_goc.py` (prompt nguyên văn microsoft/graphrag 3.3.0, 4 loại thực thể mặc định, gleaning 1, Leiden trên thành phần liên thông lớn nhất), chỉ đổi chunk thành phiên bản Điều/Khoản/Điểm; lưu ở `data/processed/ms_graphrag_goc/` và bảng `msg_*` (`db/ms_graphrag_goc.sql`, `storage/msg_store.py`).
Chỉ mục B2 bản luật (cũ): `graphrag/ms_graphrag/` (prompt tiếng Việt, trích xuất, gộp, Leiden phân cấp, báo cáo),
lưu ở bảng `ms_*` (`db/ms_graphrag.sql`, `storage/ms_store.py`) và bản sao `:ThucThe`/`:CongDong` trong Neo4j (chỉ để xem; `graph_counts` đếm riêng).
`04_load.py` xóa toàn bộ Neo4j → sau đó chạy `05 --chi-nap` để nạp lại phần B2. Kết quả trung gian và lưu đệm LLM: `data/processed/ms_graphrag/`.

Luồng trả lời của hệ thống đề xuất: `graphrag/pipeline/graph_rag.py::run(...)` phát sự kiện từng bước (backend `/api/ask/stream` gửi cho giao diện dạng NDJSON);
`answer(res, question, ngay, history=None)` gom kết quả cuối, dùng cho đánh giá.

0. **Hội thoại:** có `history` thì LLM viết lại câu hỏi tiếp nối thành câu đầy đủ (`pipeline/conversation.py`).
1. **Seed:** BM25 (pyvi tách từ, câu hỏi được thêm thuật ngữ pháp lý từ `retrieval/query_expansion.py`) và tìm vector (pgvector),
   gộp bằng RRF (`retrieval/fusion.py`), lọc theo ngày, rerank, giữ `top_k_final`. Ứng viên khớp nhưng chưa/hết hiệu lực
   được ghi chú riêng trong prompt (`prompts.format_notes`) để trả lời "chưa có hiệu lực từ …".
2. **Mở rộng đồ thị trong Neo4j** (`neo4j_store.expand_paths`): các cạnh THUOC, THAM_CHIEU, HUONG_DAN (cả hai chiều),
   ưu tiên THAM_CHIEU → HUONG_DAN → cha → con, tối đa `graph.max_expand`. Cạnh sửa đổi chỉ dùng để ghi chú "đã được … sửa đổi".
   Neo4j, embedding hoặc rerank lỗi thì pipeline vẫn trả lời (bỏ qua bước đó và ghi vào `steps`).
3. **Lọc theo ngày trong PostgreSQL:** `hieu_luc_tu <= ngay AND (hieu_luc_den IS NULL OR ngay < hieu_luc_den)`. `hieu_luc_den` là ngày **không còn** hiệu lực, nên so sánh dùng dấu `<`.
4. **Sinh câu trả lời:** LLM trả lời có trích dẫn theo mã định danh, prompt nằm trong `pipeline/prompts.py`.

Hai kho dữ liệu nối với nhau bằng **mã định danh chung**:

- PostgreSQL là nguồn dữ liệu gốc: nội dung, embedding, ngày hiệu lực, nhật ký hỏi đáp (`db/schema.sql`).
- Neo4j chỉ lưu mã định danh và quan hệ (`db/neo4j_constraints.cypher`).

**Phiên bản hiệu lực** (`docs/thiet_ke_do_thi.md`): mỗi Điều/Khoản/Điểm có thể có nhiều phiên bản trong bảng `don_vi`, cùng **mã đơn vị** `id` nhưng khác **mã phiên bản** `vid = id@hieu_luc_tu`.

- Văn bản sửa đổi không tạo mã mới cho nội dung đã sửa: nội dung mới của `ND168_2024.D6.K3.m` (do NĐ 238 sửa) là một phiên bản mới của chính mã đó.
- Tìm kiếm (BM25, vector) trả về `vid`; đổi sang mã đơn vị bằng `ids.base_id` trước khi đi đồ thị, trích dẫn hay so với gold.
- `versions.jsonl` do `graphrag/parsing/versioning.py` dựng từ `corpus.jsonl` + `amendments.jsonl` + ngày hiệu lực trong manifest.

**Mô hình đều gọi qua OpenRouter** (`graphrag/openrouter.py`), cấu hình trong `configs/base.yaml`:

| Vai trò | Mô hình |
|---|---|
| Embedding | `baai/bge-m3` (1024 chiều) |
| Rerank | `cohere/rerank-v3.5` |
| Trả lời, dựng chỉ mục B2 | `openai/gpt-6-luna` (từ 22/11; kết quả 16/11 dùng `gpt-4o-mini`) |
| LLM-judge | `openai/gpt-4o` |

Hai khóa: phần **chat** (trả lời, dựng chỉ mục B2) dùng `OPENAI_API_KEY` trước, khi khóa OpenAI hết quota thì chuyển hẳn sang OpenRouter; thứ tự ở `llm.nha_cung_cap`. Cùng mô hình `gpt-6-luna` (bỏ tiền tố `openai/`). Client tự đổi `max_tokens` → `max_completion_tokens` khi gọi OpenAI, tự bỏ `temperature`/`reasoning_effort` nếu mô hình không nhận, và đếm token (`client.usage`). Thử trước bằng `python scripts/thu_mo_hinh.py`. Embedding bge-m3 và rerank Cohere chỉ có trên OpenRouter, nên khóa OpenRouter vẫn cần còn chút hạn mức.

Muốn đổi mô hình thì chỉ sửa tên trong YAML, không sửa code. Không có mô hình nào chạy trên máy chủ, nên bản cloud 512 MB RAM chạy đúng pipeline của bản đánh giá.

**Cấu hình** (`graphrag/common/config.py::load_config(env)`):

- Đọc `base.yaml`, sau đó `local.yaml` hoặc `cloud.yaml` ghi đè lên.
- Bí mật lấy từ `.env` hoặc `.env.cloud`. Biến môi trường thật được ưu tiên hơn file.
- Chọn môi trường bằng `APP_ENV`, mặc định là `local`.

**Tài nguyên dùng chung:** `graphrag/resources.py::Resources(cfg)` tạo lười (lazy) pool PostgreSQL, driver Neo4j, embedder, LLM và chỉ mục BM25. Pipeline, backend và script đều nhận `res` thay vì tự tạo kết nối.

## Bản đồ thư mục

| Đường dẫn | Nội dung | Phụ trách |
|---|---|---|
| `graphrag/common/` | `config.py`, `ids.py` (tạo/đọc mã định danh) | TV1 |
| `graphrag/parsing/` | `docx_reader.py`, `structure_parser.py` (regex + máy trạng thái); `legal_refs.py` (đọc danh sách "điểm … khoản … Điều …"), `amendment_parser.py`, `reference_extractor.py`, `versioning.py` (dựng phiên bản) | TV2, TV1 |
| `graphrag/storage/` | `postgres.py`, `neo4j_store.py` | TV2, TV1 |
| `graphrag/retrieval/` | `bm25.py`, `fusion.py`, `rerank.py` | TV3 |
| `graphrag/embedding/`, `graphrag/llm/` | `get_embedder(cfg)`, `get_llm(cfg, role)` | TV3, TV1 |
| `graphrag/pipeline/` | `he_thong.py` (chọn hệ thống), `graph_rag.py` (đề xuất), `baseline_rag.py` (B1), `ms_graphrag.py` (B2), `prompts.py` | TV3, TV1 |
| `graphrag/ms_graphrag/` | dựng chỉ mục GraphRAG kiểu Microsoft: `indexing.py`, `prompts.py` | TV1 |
| `graphrag/evaluation/` | `metrics.py`, `judge.py`, `run_eval.py` | TV3 |
| `backend/app/` | FastAPI: routers ask, documents, graph, feedback, admin; `/health`, `/health/db` | TV1 (cloud) |
| `frontend/` | React + Vite, 4 trang: Hỏi đáp, Tra cứu, Đồ thị, Quản trị | TV3 (cloud) |
| `scripts/` | các bước xử lý dữ liệu chạy offline (00–04), công cụ tra cứu, kiểm tra câu hỏi | |
| `data/raw/` | 11 file `.docx`, đặt tên theo mã văn bản | |
| `data/eval/` | `questions_template.jsonl` (5 câu mẫu đã kiểm tra), `questions_TVx.jsonl` | cả nhóm |
| `docs/` | `thiet_ke_do_thi.md`, `huong_dan_chay_db.md` (chạy, truy vấn mẫu, theo dõi DB), `review_parser.md`, `huong_dan_gan_nhan.md`, ảnh triển khai (`anh-trien-khai/`) | |

## Dữ liệu và quy ước

- **Mã định danh** (`graphrag/common/ids.py`) có dạng `<VănBản>.D<điều>.K<khoản>.<điểm>`.
  - Ví dụ: `ND168_2024.D6.K9.b`, `L36_2024.D10`. Chương có dạng `ND168_2024.C2`.
  - Điều hoặc khoản chèn thêm có hậu tố chữ, ví dụ `D32.K9a`.
  - Luôn tạo mã bằng `make_id` / `parse_id`, không ghép chuỗi tay.
- **Một dòng trong `corpus.jsonl`** có các trường:
  - `id`, `van_ban_id`, `cap` (Chuong/Dieu/Khoan/Diem), `parent_id`, `so`, `thu_tu`, `tieu_de`;
  - `noi_dung`: chữ của riêng đơn vị đó, các đơn vị không chồng lấn nhau;
  - `ngu_canh`: tên văn bản, Điều, câu dẫn của khoản. Khi tìm kiếm thì ghép `ngu_canh` lên trước `noi_dung`, vì điểm a), b) cần câu dẫn "Phạt tiền từ … đối với…".
  - `co_trich_dan` (văn bản sửa đổi có trích nguyên văn), `so_goc`.
- **`data/manifest.csv`** là metadata của 12 văn bản (11 văn bản pháp luật và 1 văn bản hợp nhất, `vai_tro` lần lượt là `goc`, `sua_doi`, `doi_chieu`):
  - `pham_vi`: `toan_bo` hoặc `dieu:7,11`, nghĩa là chỉ lấy các Điều đó;
  - `ghi_chu`: ngoại lệ hiệu lực theo dạng `ngoại lệ: ID=YYYY-MM-DD; ...`. Ở dòng văn bản gốc, ngoại lệ là ngày hiệu lực riêng của bản gốc (`ND168_2024.D6.K3.m=2026-01-01`); ở dòng văn bản sửa đổi, khóa là **mã bị sửa** và ngày là lúc phiên bản mới bắt đầu (`ND168_2024.D20.K5.l=2028-01-01`). Bước 02 (`versioning.py`) áp các ngoại lệ này, cho cả mã con.
- **Cảnh báo của parser** nằm trong `data/processed/corpus_report.md`; kết quả review và lỗi cần sửa ở `docs/review_parser.md` (văn bản Word đánh sai chữ điểm ở NĐ 168 Điều 16, 39, 40). Đọc trước khi kết luận parser sai.
- **Câu hỏi đánh giá** soạn theo `docs/huong_dan_gan_nhan.md`.
  - Có 4 loại: `don`, `multi_hop`, `hieu_luc` (soạn theo cặp, liên kết bằng `cap_voi`), `so_sanh`.
  - Mã câu hỏi theo người soạn: TV1 dùng q1001…, TV2 q2001…, TV3 q3001….
  - `gold_ids` là mã đơn vị của văn bản bị sửa (không ghi mã văn bản sửa đổi); mã văn bản sửa đổi ghi ở `nguon_sua_doi`.
  - **Không dùng LLM để viết đáp án hoặc gold**, chỉ được dùng LLM để gợi ý câu hỏi.

## Trạng thái (cập nhật 05/11/2026)

**05/11:** thêm hai baseline và chọn hệ thống: B1 Hybrid RAG (`baseline_rag.py`), B2 GraphRAG kiểu Microsoft (`ms_graphrag.py`,
`graphrag/ms_graphrag/`, `scripts/05_ms_graphrag_index.py`); API `he_thong`/`che_do`, `GET /api/systems`; giao diện chọn hệ thống
và chế độ So sánh ba cột; `chay_bo_test.py --he-thong …` (6 độ đo không LLM + paired bootstrap; quyết định 05/11: không dùng LLM-judge/RAGAS). Mới kiểm thử bằng LLM/embedding giả
(`tests/test_ms_graphrag.py`, PostgreSQL thật). **Việc tiếp theo:** chạy `05 --gioi-han 100` với OpenRouter thật, xem
`data/processed/ms_graphrag/thong_ke.md`, rồi chạy toàn bộ; sau khi nhóm rà soát xong bộ câu thì chạy so sánh 3 hệ thống.

**28/10:** dữ liệu đã nạp vào PostgreSQL + Neo4j trên máy (3.078 node, 5.201 cạnh). Đã có `graph_rag.run/answer` (GraphRAG v0 +
hội thoại + streaming), API `/api/ask/stream`, `/api/units/search`, `/api/amended`, `/api/overview`, frontend 5 trang
(Trò chuyện, Tra cứu văn bản, Lịch sử sửa đổi, Khám phá đồ thị, Thống kê), kịch bản demo `docs/kich_ban_demo.md`.
Pipeline mới chỉ kiểm thử bằng bản giả (`tests/test_graph_rag.py`) và PostgreSQL thật; **chưa chạy với OpenRouter + Neo4j thật**:
chạy `python scripts/kiem_tra_demo.py` trên máy nhóm. Baseline B1–B3 tạm hoãn đến sau buổi demo.

**Đã xong (code và dữ liệu trong repo):**

- Dữ liệu: 11 văn bản + VBHN, `manifest.csv` đủ ngày hiệu lực; corpus 2.997 đơn vị (đã review, `docs/review_parser.md`).
- Bước 2 đủ: `amendment_parser` (397 thao tác sửa đổi), `versioning` (3.356 phiên bản), `reference_extractor` (1.733 dẫn chiếu).
- Bước 4 `04_load.py`: nạp PostgreSQL và Neo4j (đã chạy trên máy nhóm 25/10).
- Thiết kế đồ thị và phiên bản (`docs/thiet_ke_do_thi.md`); prompt sinh câu trả lời + tách trích dẫn (`pipeline/prompts.py`, `scripts/thu_prompt.py`).
- Client OpenRouter, embedder, rerank, BM25, RRF; các truy vấn đọc trong `postgres.py`; độ đo trong `metrics.py`.
- Khung backend (đủ API) và frontend; Dockerfile; `render.yaml`. 30 test.

**Môn Cloud (24/10):** đã có Dockerfile, `render.yaml`, khung backend đủ API, frontend 4 trang, báo cáo sơ bộ; **chưa deploy**,
chưa có tài khoản Render/Supabase/AuraDB trong repo; thiếu `ci.yml`, `.env.cloud.example`. Bước tiếp theo: "Hello cloud" (tuần 26/10).

**Chưa chạy trên máy nhóm (kiểm tra 24/10):** chưa bật Docker lần nào (không có `db/volumes`), chưa có `embedding.npy`,
`.env` có thể còn thiếu `OPENROUTER_API_KEY`; repo còn thiếu `.github/workflows/ci.yml` và `.env.cloud.example`.

**Việc tiếp theo, theo thứ tự:**

1. ~~Bật Docker → 02 → 03 → 04~~ đã xong 25/10. Trước demo: `python scripts/kiem_tra_demo.py`, sửa câu XEM LẠI: TV1.
2. ~~`baseline_rag.py`~~ đã xong 05/11 (B1 Hybrid RAG; B2 là GraphRAG kiểu Microsoft).
3. `graph_rag` v0 đã có (28/10); v1 theo `docs/thiet_ke_do_thi.md` mục 7 sau demo: TV1.
4. ~~`run_eval.py`~~ gọi `chay_bo_test.py` (05/11); còn `evaluation/judge.py`: TV3.
5. Sau khi hệ thống chạy được: soạn bộ câu hỏi (~200 câu) theo `docs/huong_dan_gan_nhan.md`: cả nhóm.
6. Song song: sửa 2 lỗi parser, kiểm tra tay thao tác sửa đổi và dẫn chiếu (`huong_dan_chay_db.md` mục 7): TV2.
   Nhập tay sửa đổi "đoạn thứ hai" của NĐ 238 khoản 2 Điều 17. Bảng `HUONG_DAN` lập tay (`data/reference/huong_dan.csv`): TV1 + TV2.

Backend tự đổi `NotImplementedError` thành mã HTTP 501, nên API vẫn chạy khi một phần chưa xong.

## Quy tắc khi sửa code

- **Không viết cứng** tên mô hình, tham số top-k hay đường dẫn trong code. Đọc từ `cfg` và thêm khóa mới vào `configs/base.yaml`.
- **Một pipeline cho cả hai môn:** backend, script và đánh giá cùng gọi `graph_rag.answer` / `baseline_rag.answer`. Không viết pipeline riêng cho cloud.
- **Hai hàm trả lời cùng định dạng kết quả:** `{'answer', 'citations', 'units', 'retrieved_ids', 'latency_s'}`. `run_eval.py` và API dựa vào định dạng này.
- **SQL luôn dùng tham số** (`%(ten)s`). Tên cột vector chỉ được lấy trong `VECTOR_COLUMNS`.
- **Backend không được import `torch` hay `sentence_transformers`.** Render free chỉ có 512 MB RAM. Provider `local` chỉ dùng trên máy có GPU, cần `pip install -e ".[ml]"`.
- **Lưu đệm kết quả gọi LLM** vào `data/processed/cache/` (đã có trong gitignore), để sửa độ đo không phải gọi lại API và tốn tiền.
- **Test:** thêm test trong `tests/` cho mỗi hàm mới. Test gọi OpenRouter phải dùng `httpx.MockTransport`, không gọi API thật.
- **Comment, docstring, tên biến nghiệp vụ viết bằng tiếng Việt**, giống code hiện có (`van_ban`, `don_vi`, `hieu_luc_tu`, `ngay`).
- **Sửa parser xong phải chạy lại** `01_parse.py`, xem `corpus_report.md`, và kiểm tra số Điều/Khoản/Điểm không đổi bất thường. Mã định danh đổi sẽ làm hỏng gold trong bộ câu hỏi.

## Môn Điện toán đám mây: triển khai lên Render

Cùng repo, cùng pipeline với môn NLP; chỉ khác kết nối DB (`APP_ENV=cloud`). Tài liệu môn Cloud (báo cáo sơ bộ,
kế hoạch triển khai) nằm ngoài repo, ở thư mục `NLP/Cloud/` của nhóm.

**Kiến trúc triển khai** (tất cả gói miễn phí, không nhập thẻ; OpenRouter là credit trả trước):

| Thành phần | Dịch vụ | Cấu hình trong repo |
|---|---|---|
| Backend FastAPI | Render **Web Service**, Docker, Free 512 MB, khu vực Singapore | `backend/Dockerfile`, `render.yaml` |
| Frontend React | Render **Static Site** | `frontend/`, biến `VITE_API_URL` |
| PostgreSQL + pgvector | Supabase Free (500 MB, tự dừng sau 7 ngày ít dùng) | `db/schema.sql` |
| Đồ thị | Neo4j AuraDB Free (50.000 node / 175.000 cạnh, tự dừng sau 3 ngày) | `db/neo4j_constraints.cypher` |
| Mô hình | OpenRouter (key riêng cho bản cloud, có hạn mức) | `configs/base.yaml` + `configs/cloud.yaml` (`max_tokens` 800) |
| Mã nguồn, CI | GitHub (push `main` → Render tự deploy), GitHub Actions | `.github/workflows/ci.yml` (**còn thiếu**) |

Phương án dự phòng: nếu backend vượt 512 MB RAM thì chuyển backend sang Vercel (2 GB, serverless).

**Các bước triển khai** (chi tiết: `README.md` mục "Triển khai lên cloud"; ảnh chụp đặt tên theo `docs/anh-trien-khai/README.md`, B1–B9):

1. Supabase: tạo project Singapore. AuraDB: tạo instance Free, **tải file mật khẩu ngay** (chỉ hiện một lần).
2. Trên máy nhóm: `copy .env.cloud.example .env.cloud` (**file mẫu còn thiếu trong repo**), điền `DATABASE_URL`
   (Supabase → Connect → **Session pooler**, IPv4), `NEO4J_URI` (`neo4j+s://…`), `NEO4J_USER`, `NEO4J_PASSWORD`,
   `OPENROUTER_API_KEY`, `ADMIN_PASSWORD`, `CORS_ORIGINS`.
3. Nạp dữ liệu lên cloud: `python scripts/04_load.py --env cloud`. Script tự chạy `schema.sql` và ràng buộc Neo4j,
   dùng lại `embedding.npy` đã tính trên máy (không gọi lại bge-m3 cho kho văn bản).
4. Render → New → Web Service: Language **Docker**, Root Directory để trống, Dockerfile Path `./backend/Dockerfile`,
   Docker Build Context `.`, Instance **Free**, Health Check Path `/health`; khai báo các biến ở bước 2 trong Environment.
   Kiểm tra `/health`, `/health/db`, `/docs`.
5. Render → New → Static Site: Root Directory `frontend`, Build `npm ci && npm run build`, Publish `dist`,
   `VITE_API_URL` = địa chỉ Web Service, Rewrite `/*` → `/index.html`.
6. Đặt `CORS_ORIGINS` của Web Service = địa chỉ Static Site, deploy lại. Hoặc tạo cả hai dịch vụ một lần bằng `render.yaml` (New → Blueprint).

Thử image backend giống trên Render ngay trên máy: `docker compose -f db/docker-compose.yml --profile api up -d --build` (cần `.env.cloud`).

**Ràng buộc khi viết code cho bản cloud:**

- Backend chỉ cài nhóm `api` (+ thư viện lõi); không import `torch`, `sentence_transformers`, không tải mô hình.
- Backend khởi động phải nhanh và không cần DB: `Resources` tạo kết nối, chỉ mục BM25 khi dùng lần đầu; `/health` không chạm DB.
- Mọi bí mật đọc từ biến môi trường; không ghi đường dẫn, URL, key vào code. Thêm biến mới thì cập nhật `.env.example`,
  `.env.cloud.example` và `render.yaml` (`sync: false`).
- Gói Free tắt sau 15 phút không truy cập (mở lại mất khoảng 1 phút); trang frontend đã hiện thông báo "Đang kết nối máy chủ…".
- Pool kết nối Supabase nhỏ (`make_pool`, `max_size` 4) và có kiểm tra kết nối trước khi dùng, vì pooler đóng kết nối nhàn rỗi.

**Chức năng web** (router trong `backend/app/routers/`, trang trong `frontend/src/pages/`):
F1 Hỏi đáp `POST /api/ask/stream` (NDJSON: step, context, token, done) và `POST /api/ask` · F2 Tra cứu `GET /api/documents`,
`/api/documents/{id}/units?date=`, `/api/units/search?q=`, `/api/units/{id}`, `/api/amended` · F3 Đồ thị `GET /api/graph/{id}` ·
F4 Đánh giá `POST /api/feedback` · F5 Thống kê `GET /api/overview` (công khai), `GET /api/admin/stats` (header `X-Admin-Password`).

**Kế hoạch môn Cloud:**

| Thời gian | Bước | Kết quả |
|---|---|---|
| 19/10 – 25/10 | Tìm hiểu, tạo tài khoản Render / Supabase / AuraDB, vẽ use case, ERD, sơ đồ tuần tự, sơ đồ triển khai | Đủ tài khoản, bản phân tích thiết kế |
| 26/10 – 01/11 | "Hello cloud": deploy backend (`/health`) và frontend, kết nối thử 2 DB | Hai địa chỉ `*.onrender.com` chạy được |
| 02/11 – 08/11 | Dữ liệu lên cloud (`04_load.py --env cloud`) | F2, F3 chạy trên cloud |
| 09/11 – 15/11 | Đưa `graph_rag.answer` vào `/api/ask`, hoàn thiện giao diện | F1, F4 chạy trên cloud |
| 16/11 – 22/11 | Trang quản trị, kiểm thử trên điện thoại, đo thời gian phản hồi | Sản phẩm ổn định |
| 23/11 – 29/11 | Báo cáo (~20 trang, 7 mục), slide, demo, video dự phòng | Hồ sơ nộp |

Phân công: TV1 backend + Web Service + key OpenRouter; TV2 Supabase + AuraDB + nạp dữ liệu; TV3 frontend + Static Site + theo dõi chi phí hằng tuần.
Trước buổi demo: Resume AuraDB, mở dashboard Supabase, mở trang web trước 2–3 phút.

## Bảo mật và chi phí

- **Không commit** `.env`, `.env.cloud`, API key hay mật khẩu. `.gitignore` đã chặn mọi file `.env*` trừ hai file mẫu. Lỡ lộ key thì thu hồi trên OpenRouter ngay.
- **Mỗi người dùng một key OpenRouter riêng có hạn mức chi tiêu.** Trước khi chạy đánh giá trên cả bộ câu hỏi bằng `gpt-4o`, ước tính chi phí trước.
- **Bản cloud:** không nhập thẻ cho Render, Supabase, AuraDB (màn hình nào đòi thẻ thì dừng lại). Key OpenRouter của
  bản cloud tách riêng, đặt hạn mức, không bật tự nạp tiền. Che key và mật khẩu trong ảnh chụp đưa vào báo cáo.

## Quy trình Git

- Nhánh `main` luôn chạy được và Render deploy từ nhánh này. Mỗi người làm trên nhánh riêng, ví dụ `tv2/load-postgres`, rồi mở Pull Request để nhóm trưởng review.
- Trước khi mở PR, chạy `python -m pytest -q`. Nếu có câu hỏi mới, chạy thêm `check_questions.py`.
- Không commit `.npy`, `data/processed/cache/` hay `node_modules`. Chia sẻ `embedding.npy` qua Drive của nhóm.
