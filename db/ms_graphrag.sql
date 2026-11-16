-- Chỉ mục GraphRAG kiểu Microsoft (baseline B2), tách riêng khỏi dữ liệu văn bản (don_vi).
-- Tạo bởi scripts/05_ms_graphrag_index.py; chạy lại an toàn. Không ảnh hưởng hệ thống đề xuất và B1.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ms_thuc_the (
  id         TEXT PRIMARY KEY,          -- tên đã chuẩn hóa (khóa gộp)
  ten        TEXT NOT NULL,
  loai       TEXT NOT NULL,             -- HANH_VI / PHUONG_TIEN / CHU_THE / CHE_TAI / DIEU_KIEN / GIAY_TO / CO_QUAN / KHAI_NIEM
  mo_ta      TEXT,
  tan_suat   INTEGER,                   -- số đơn vị văn bản nhắc tới
  bac        INTEGER,                   -- số quan hệ
  embedding  vector(1024)
);

CREATE TABLE IF NOT EXISTS ms_quan_he (
  nguon      TEXT NOT NULL,
  dich       TEXT NOT NULL,
  mo_ta      TEXT,
  trong_so   REAL,
  tan_suat   INTEGER,
  PRIMARY KEY (nguon, dich)
);
CREATE INDEX IF NOT EXISTS idx_ms_quan_he_dich ON ms_quan_he (dich);

-- Thực thể xuất hiện trong phiên bản nào của điều khoản nào (đơn vị văn bản của GraphRAG)
CREATE TABLE IF NOT EXISTS ms_lien_ket (
  thuc_the_id TEXT NOT NULL,
  vid         TEXT NOT NULL,
  don_vi_id   TEXT NOT NULL,
  PRIMARY KEY (thuc_the_id, vid)
);
CREATE INDEX IF NOT EXISTS idx_ms_lien_ket_don_vi ON ms_lien_ket (don_vi_id);

CREATE TABLE IF NOT EXISTS ms_cong_dong (
  id         TEXT PRIMARY KEY,          -- '<cấp>-<số>'
  cap        INTEGER NOT NULL,          -- 0 = cấp cao nhất
  cha        TEXT,
  so_thanh_vien INTEGER,
  tieu_de    TEXT,
  tom_tat    TEXT,
  bao_cao    TEXT,                      -- báo cáo đầy đủ (markdown)
  muc_do     REAL,                      -- mức độ quan trọng 0–10 do LLM chấm
  embedding  vector(1024)
);

CREATE TABLE IF NOT EXISTS ms_thanh_vien (
  cong_dong_id TEXT NOT NULL,
  thuc_the_id  TEXT NOT NULL,
  PRIMARY KEY (cong_dong_id, thuc_the_id)
);
CREATE INDEX IF NOT EXISTS idx_ms_thanh_vien_tt ON ms_thanh_vien (thuc_the_id);

CREATE INDEX IF NOT EXISTS idx_ms_thuc_the_emb ON ms_thuc_the USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_ms_cong_dong_emb ON ms_cong_dong USING hnsw (embedding vector_cosine_ops);
