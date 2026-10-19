-- Lược đồ PostgreSQL: nguồn dữ liệu gốc (nội dung, embedding, hiệu lực).
-- Chạy được cả trên máy (Docker tự chạy khi khởi tạo) và trên Supabase (dán vào SQL Editor).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS van_ban (
  id            TEXT PRIMARY KEY,      -- 'ND168_2024'
  so_hieu       TEXT NOT NULL,         -- '168/2024/NĐ-CP'
  ten           TEXT,
  loai          TEXT NOT NULL,         -- Luật / Nghị định / Thông tư / VBHN
  co_quan       TEXT,
  ngay_ban_hanh DATE,
  hieu_luc_tu   DATE,
  vai_tro       TEXT,                  -- goc / sua_doi / doi_chieu
  sua_doi_cho   TEXT                   -- mã văn bản bị sửa (nếu là văn bản sửa đổi)
);

CREATE TABLE IF NOT EXISTS don_vi (
  id            TEXT PRIMARY KEY,      -- 'ND168_2024.D6.K5.a'
  van_ban_id    TEXT NOT NULL REFERENCES van_ban(id),
  cap           TEXT NOT NULL,         -- Chuong / Dieu / Khoan / Diem
  parent_id     TEXT,
  so            TEXT,                  -- số hiệu đơn vị: '6', '5', 'a'
  thu_tu        INTEGER,               -- thứ tự xuất hiện trong văn bản (để hiển thị)
  tieu_de       TEXT,
  noi_dung      TEXT NOT NULL,         -- chữ của riêng đơn vị (nguyên văn)
  ngu_canh      TEXT,                  -- văn bản, Điều, câu dẫn khoản: ghép trước noi_dung khi tìm kiếm
  embedding     vector(1024),          -- bge-m3 (qua OpenRouter hoặc chạy trên máy)
  hieu_luc_tu   DATE NOT NULL,
  hieu_luc_den  DATE                   -- NULL = còn hiệu lực
);

CREATE INDEX IF NOT EXISTS idx_don_vi_embedding ON don_vi USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_don_vi_hieu_luc ON don_vi (hieu_luc_tu, hieu_luc_den);
CREATE INDEX IF NOT EXISTS idx_don_vi_van_ban ON don_vi (van_ban_id, thu_tu);

-- Nhật ký hỏi đáp: đánh giá câu trả lời (F4) và thống kê cho quản trị (F5)
CREATE TABLE IF NOT EXISTS hoi_dap_log (
  id            BIGSERIAL PRIMARY KEY,
  thoi_gian     TIMESTAMPTZ NOT NULL DEFAULT now(),
  cau_hoi       TEXT NOT NULL,
  ngay_ap_dung  DATE,
  he_thong      TEXT,                  -- GRAPH / B1 / B2 / B3
  tra_loi       TEXT,
  trich_dan     TEXT[],
  latency_ms    INTEGER,
  danh_gia      SMALLINT CHECK (danh_gia IN (-1, 1)),   -- 1 hữu ích, -1 chưa đúng
  ghi_chu       TEXT
);
CREATE INDEX IF NOT EXISTS idx_hoi_dap_thoi_gian ON hoi_dap_log (thoi_gian);
