-- Chỉ mục B2 theo GraphRAG GỐC của Microsoft (chỉ đổi chunk thành Điều/Khoản/Điểm), tách riêng khỏi bản đã chỉnh (ms_*).
-- Tạo bởi scripts/05_ms_graphrag_index.py --ban goc; chạy lại an toàn. Không ảnh hưởng hệ thống đề xuất và B1.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS msg_text_unit (
  ma_ngan    INTEGER PRIMARY KEY,       -- id ngắn dùng trong ngữ cảnh "Sources" và trích dẫn [Data: Sources (…)]
  vid        TEXT NOT NULL,             -- phiên bản điều khoản (don_vi.vid)
  don_vi_id  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_text_unit_vid ON msg_text_unit (vid);

CREATE TABLE IF NOT EXISTS msg_thuc_the (
  id         TEXT PRIMARY KEY,          -- tên đã chuẩn hóa (khóa gộp)
  ten        TEXT NOT NULL,             -- tên viết hoa như bản gốc
  loai       TEXT,                      -- ORGANIZATION / PERSON / GEO / EVENT (hoặc loại khác LLM tự đặt)
  mo_ta      TEXT,
  tan_suat   INTEGER,
  bac        INTEGER,                   -- degree (number of relationships)
  ma_ngan    INTEGER,
  embedding  vector(1024)               -- bge-m3 của "tên:mô tả"
);

CREATE TABLE IF NOT EXISTS msg_quan_he (
  nguon        TEXT NOT NULL,
  dich         TEXT NOT NULL,
  mo_ta        TEXT,
  trong_so     REAL,
  tan_suat     INTEGER,
  bac_ket_hop  INTEGER,                 -- combined_degree (rank của quan hệ)
  ma_ngan      INTEGER,
  vids         TEXT[],                  -- text unit nơi quan hệ được trích
  PRIMARY KEY (nguon, dich)
);
CREATE INDEX IF NOT EXISTS idx_msg_quan_he_dich ON msg_quan_he (dich);

CREATE TABLE IF NOT EXISTS msg_lien_ket (
  thuc_the_id TEXT NOT NULL,
  vid         TEXT NOT NULL,
  don_vi_id   TEXT NOT NULL,
  PRIMARY KEY (thuc_the_id, vid)
);

CREATE TABLE IF NOT EXISTS msg_cong_dong (
  id         TEXT PRIMARY KEY,
  cap        INTEGER NOT NULL,
  cha        TEXT,
  so_thanh_vien INTEGER,
  tieu_de    TEXT,
  tom_tat    TEXT,
  bao_cao    TEXT,                      -- full_content
  muc_do     REAL,                      -- rating
  embedding  vector(1024)
);

CREATE TABLE IF NOT EXISTS msg_thanh_vien (
  cong_dong_id TEXT NOT NULL,
  thuc_the_id  TEXT NOT NULL,
  PRIMARY KEY (cong_dong_id, thuc_the_id)
);
CREATE INDEX IF NOT EXISTS idx_msg_thanh_vien_tt ON msg_thanh_vien (thuc_the_id);

CREATE INDEX IF NOT EXISTS idx_msg_thuc_the_emb ON msg_thuc_the USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_msg_cong_dong_emb ON msg_cong_dong USING hnsw (embedding vector_cosine_ops);
