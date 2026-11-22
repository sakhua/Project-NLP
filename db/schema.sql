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

-- Mỗi dòng là MỘT PHIÊN BẢN của một Điều/Khoản/Điểm (thiết kế: docs/thiet_ke_do_thi.md).
-- Cùng một mã đơn vị (id) có thể có nhiều phiên bản: bản gốc và các bản sau sửa đổi, nối tiếp nhau theo thời gian.
-- Nạp từ data/processed/versions.jsonl (scripts/02_extract_relations.py).
CREATE TABLE IF NOT EXISTS don_vi (
  vid            TEXT PRIMARY KEY,      -- mã phiên bản 'ND168_2024.D6.K3.m@2026-08-15' = id@hieu_luc_tu
  id             TEXT NOT NULL,         -- mã đơn vị 'ND168_2024.D6.K3.m' (trích dẫn, gold, node Neo4j dùng mã này)
  van_ban_id     TEXT NOT NULL REFERENCES van_ban(id),
  cap            TEXT NOT NULL,         -- Chuong / Dieu / Khoan / Diem
  parent_id      TEXT,
  so             TEXT,                  -- số hiệu đơn vị: '6', '5', 'a', '1a', 'k1'
  thu_tu         REAL,                  -- thứ tự trong văn bản (đơn vị chèn thêm có số lẻ, vd. 78.5)
  tieu_de        TEXT,
  noi_dung       TEXT NOT NULL,         -- chữ của riêng đơn vị (nguyên văn, theo phiên bản này)
  ngu_canh       TEXT,                  -- văn bản, Điều, câu dẫn khoản: ghép trước noi_dung khi tìm kiếm
  embedding      vector(1024),          -- bge-m3 của ngu_canh + noi_dung (qua OpenRouter hoặc chạy trên máy)
  hieu_luc_tu    DATE NOT NULL,
  hieu_luc_den   DATE,                  -- ngày KHÔNG còn hiệu lực (so sánh ngay < hieu_luc_den); NULL = đang hiệu lực
  nguon_sua_doi  TEXT,                  -- đơn vị của văn bản sửa đổi tạo ra phiên bản này; NULL = bản gốc
  loai_phien_ban TEXT NOT NULL DEFAULT 'goc',   -- goc / sua_doi / thay_the / bo_sung
  UNIQUE (id, hieu_luc_tu),
  CHECK (hieu_luc_den IS NULL OR hieu_luc_den >= hieu_luc_tu)
);

CREATE INDEX IF NOT EXISTS idx_don_vi_id ON don_vi (id);
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

-- Tài khoản đăng nhập giao diện web (không có đăng ký: tạo bằng scripts/tao_tai_khoan.py; backend tự tạo bảng nếu thiếu)
CREATE TABLE IF NOT EXISTS tai_khoan (
  id               BIGSERIAL PRIMARY KEY,
  ten_dang_nhap    TEXT UNIQUE NOT NULL,
  mat_khau_bam     TEXT NOT NULL,            -- pbkdf2_sha256$số_vòng$muối$băm
  ho_ten           TEXT,
  hoat_dong        BOOLEAN NOT NULL DEFAULT true,
  tao_luc          TIMESTAMPTZ NOT NULL DEFAULT now(),
  dang_nhap_cuoi   TIMESTAMPTZ,
  so_lan_dang_nhap INTEGER NOT NULL DEFAULT 0
);
ALTER TABLE hoi_dap_log ADD COLUMN IF NOT EXISTS tai_khoan_id BIGINT REFERENCES tai_khoan(id);
