"""Truy cập PostgreSQL + pgvector (local: Docker; cloud: Supabase).

Phụ trách: TV2 (ghi dữ liệu, truy vấn tra cứu), TV3 (tìm vector).
Mọi hàm nhận `conn` là một kết nối psycopg (lấy từ Resources.pg_pool.connection()).

Bảng don_vi lưu PHIÊN BẢN (docs/thiet_ke_do_thi.md): khóa là `vid` = 'mã@hiệu lực từ', cột `id` là mã đơn vị.
  - Tìm kiếm (BM25, vector) trả về vid: mỗi phiên bản là một ứng viên.
  - fetch_valid(ids, ngay) nhận MÃ ĐƠN VỊ và trả về đúng phiên bản có hiệu lực tại ngày đó.
  - Đổi vid -> mã đơn vị bằng graphrag.common.ids.base_id.
"""
from __future__ import annotations

from datetime import date

VECTOR_COLUMNS = {"embedding"}   # chỉ cho phép tên cột này trong SQL (tránh SQL injection)

SQL_VECTOR_SEARCH = """
SELECT vid, 1 - ({col} <=> %(qvec)s::vector) AS score
FROM don_vi
WHERE cap IN ('Khoan', 'Diem', 'Dieu') AND {col} IS NOT NULL
ORDER BY {col} <=> %(qvec)s::vector
LIMIT %(k)s;
"""

SQL_VALID = "hieu_luc_tu <= %(ngay)s AND (hieu_luc_den IS NULL OR %(ngay)s < hieu_luc_den)"

SQL_FETCH_VALID = f"""
SELECT vid, id, van_ban_id, cap, tieu_de, noi_dung, ngu_canh, hieu_luc_tu, hieu_luc_den,
       nguon_sua_doi, loai_phien_ban
FROM don_vi
WHERE id = ANY(%(ids)s) AND {SQL_VALID};
"""


def make_pool(cfg: dict, max_size: int = 4):
    """Pool kết nối dùng chung cho backend (nhiều request cùng lúc)."""
    from pgvector.psycopg import register_vector
    from psycopg_pool import ConnectionPool

    # check: kiểm tra kết nối trước khi dùng (pooler của Supabase có thể đóng kết nối nhàn rỗi)
    return ConnectionPool(cfg["postgres"]["dsn"], min_size=1, max_size=max_size, timeout=10,
                          configure=register_vector, check=ConnectionPool.check_connection, open=True)


def connect(cfg: dict):
    """Một kết nối đơn, dùng cho script nạp dữ liệu và chạy đánh giá."""
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(cfg["postgres"]["dsn"])
    try:
        register_vector(conn)
    except psycopg.ProgrammingError:     # DB mới tạo, chưa chạy schema.sql (chưa có extension vector)
        conn.rollback()
    return conn


def _rows(cur) -> list[dict]:
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------- Ghi dữ liệu (scripts/04_load.py) ----------
DON_VI_COLS = ["vid", "id", "van_ban_id", "cap", "parent_id", "so", "thu_tu", "tieu_de", "noi_dung", "ngu_canh",
               "hieu_luc_tu", "hieu_luc_den", "nguon_sua_doi", "loai_phien_ban"]
VAN_BAN_COLS = ["id", "so_hieu", "ten", "loai", "co_quan", "ngay_ban_hanh", "hieu_luc_tu", "vai_tro", "sua_doi_cho"]


def apply_schema(conn, schema_sql: str, recreate_don_vi: bool = False) -> None:
    """Chạy db/schema.sql (an toàn khi chạy lại). recreate_don_vi: xóa bảng don_vi cũ (khác lược đồ) trước."""
    with conn.cursor() as cur:
        if recreate_don_vi:
            cur.execute("DROP TABLE IF EXISTS don_vi CASCADE")
        cur.execute(schema_sql)
    conn.commit()
    from pgvector.psycopg import register_vector

    register_vector(conn)


def don_vi_has_vid(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'don_vi' AND column_name = 'vid'")
        return cur.fetchone() is not None


def clear_data(conn) -> None:
    """Xóa văn bản và phiên bản (giữ nguyên nhật ký hỏi đáp) để nạp lại từ đầu."""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE don_vi")     # TRUNCATE trả lại dung lượng ngay (DELETE để lại "dòng chết", tốn chỗ trên Supabase)
        cur.execute("DELETE FROM van_ban")
    conn.commit()


def upsert_van_ban(conn, rows: list[dict]) -> None:
    """rows: các dòng của data/manifest.csv (ô trống = NULL)."""
    data = [[(r.get(c) or None) for c in VAN_BAN_COLS] for r in rows]
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in VAN_BAN_COLS[1:])
    with conn.cursor() as cur:
        cur.executemany(f"INSERT INTO van_ban ({', '.join(VAN_BAN_COLS)}) VALUES ({', '.join(['%s'] * len(VAN_BAN_COLS))}) "
                        f"ON CONFLICT (id) DO UPDATE SET {sets}", data)
    conn.commit()


def upsert_don_vi(conn, rows: list[dict], batch: int = 500) -> None:
    """rows: các dòng của data/processed/versions.jsonl (mỗi dòng một phiên bản, đủ cột của bảng don_vi trừ embedding)."""
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in DON_VI_COLS[1:])
    sql = (f"INSERT INTO don_vi ({', '.join(DON_VI_COLS)}) VALUES ({', '.join(['%s'] * len(DON_VI_COLS))}) "
           f"ON CONFLICT (vid) DO UPDATE SET {sets}")
    with conn.cursor() as cur:
        for i in range(0, len(rows), batch):
            cur.executemany(sql, [[r.get(c) for c in DON_VI_COLS] for r in rows[i:i + batch]])
    conn.commit()


def update_embeddings(conn, vids: list[str], vectors, column: str = "embedding", batch: int = 500) -> int:
    """vids: data/processed/embedding_ids.json (mã phiên bản), vectors: embedding.npy cùng thứ tự. Trả về số dòng đã ghi."""
    if column not in VECTOR_COLUMNS:
        raise ValueError(column)
    import numpy as np

    n = 0
    with conn.cursor() as cur:
        for i in range(0, len(vids), batch):
            data = [(np.asarray(v, dtype=np.float32), vid) for vid, v in zip(vids[i:i + batch], vectors[i:i + batch])]
            cur.executemany(f"UPDATE don_vi SET {column} = %s WHERE vid = %s", data)
            n += len(data)
    conn.commit()
    return n


def summary(conn) -> dict:
    """Số liệu để in sau khi nạp (và chụp màn hình cho báo cáo)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT van_ban_id, count(*) AS phien_ban, count(DISTINCT id) AS don_vi,
                              count(*) FILTER (WHERE hieu_luc_den IS NOT NULL) AS da_het_hieu_luc,
                              count(embedding) AS co_embedding
                       FROM don_vi GROUP BY van_ban_id ORDER BY van_ban_id""")
        rows = _rows(cur)
        cur.execute(f"SELECT count(*) FROM don_vi WHERE {SQL_VALID}", {"ngay": date.today()})
        con_hieu_luc = cur.fetchone()[0]
        cur.execute("SELECT pg_size_pretty(pg_total_relation_size('don_vi'))")
        size = cur.fetchone()[0]
    return {"theo_van_ban": rows, "dang_hieu_luc_hom_nay": con_hieu_luc, "dung_luong_don_vi": size}


# ---------- Truy xuất (pipeline) ----------
def all_unit_texts(conn) -> tuple[list[str], list[str]]:
    """(vids, nội dung) của mọi phiên bản Điều/Khoản/Điểm, để dựng chỉ mục BM25 khi khởi động."""
    with conn.cursor() as cur:
        cur.execute("SELECT vid, coalesce(ngu_canh || E'\\n', '') || noi_dung FROM don_vi "
                    "WHERE cap IN ('Khoan','Diem','Dieu') ORDER BY vid")
        rows = cur.fetchall()
    return [r[0] for r in rows], [r[1] for r in rows]


def vector_search(conn, qvec, k: int = 50, column: str = "embedding") -> list[tuple[str, float]]:
    """[(vid, điểm cosine)], gồm mọi phiên bản; lọc theo ngày ở fetch_valid."""
    if column not in VECTOR_COLUMNS:
        raise ValueError(column)
    with conn.cursor() as cur:
        cur.execute(SQL_VECTOR_SEARCH.format(col=column), {"qvec": qvec, "k": k})
        return [(r[0], float(r[1])) for r in cur.fetchall()]


def fetch_valid(conn, ids: list[str], ngay: date) -> list[dict]:
    """ids: MÃ ĐƠN VỊ. Trả về phiên bản có hiệu lực tại `ngay` của từng mã (mã đã hết hiệu lực / chưa có hiệu lực thì không có)."""
    with conn.cursor() as cur:
        cur.execute(SQL_FETCH_VALID, {"ids": ids, "ngay": ngay})
        return _rows(cur)


# ---------- Tra cứu (API /api/documents, /api/units) ----------
def list_van_ban(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""SELECT v.id, v.so_hieu, v.ten, v.loai, v.co_quan, v.ngay_ban_hanh, v.hieu_luc_tu, v.vai_tro,
                              v.sua_doi_cho, count(DISTINCT d.id) AS so_don_vi,
                              count(DISTINCT d.id) FILTER (WHERE d.cap = 'Dieu') AS so_dieu
                       FROM van_ban v LEFT JOIN don_vi d ON d.van_ban_id = v.id
                       GROUP BY v.id ORDER BY v.vai_tro = 'goc' DESC, v.hieu_luc_tu DESC NULLS LAST, v.id""")
        return _rows(cur)


def list_units_valid(conn, van_ban_id: str, ngay: date) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(f"""SELECT vid, id, cap, parent_id, so, tieu_de, noi_dung, hieu_luc_tu, hieu_luc_den,
                               nguon_sua_doi, loai_phien_ban
                        FROM don_vi WHERE van_ban_id = %(vb)s AND {SQL_VALID}
                        ORDER BY thu_tu NULLS LAST, id""", {"vb": van_ban_id, "ngay": ngay})
        return _rows(cur)


def get_units(conn, ids: list[str]) -> list[dict]:
    """Mọi phiên bản của các mã đơn vị (không lọc ngày) – để hiển thị lịch sử sửa đổi."""
    with conn.cursor() as cur:
        cur.execute("""SELECT vid, id, van_ban_id, cap, tieu_de, noi_dung, hieu_luc_tu, hieu_luc_den,
                              nguon_sua_doi, loai_phien_ban
                       FROM don_vi WHERE id = ANY(%(ids)s) ORDER BY id, hieu_luc_tu""", {"ids": ids})
        return _rows(cur)


def latest_versions(conn, ids: list[str]) -> dict[str, dict]:
    """Phiên bản mới nhất của từng mã (khi tắt lọc theo ngày, và để hiển thị tên/nội dung trên đồ thị)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (id) vid, id, van_ban_id, cap, tieu_de, noi_dung, ngu_canh,
                              hieu_luc_tu, hieu_luc_den, nguon_sua_doi, loai_phien_ban
                       FROM don_vi WHERE id = ANY(%(ids)s) ORDER BY id, hieu_luc_tu DESC""", {"ids": ids})
        return {r["id"]: r for r in _rows(cur)}


def search_units_by_id(conn, prefix: str, limit: int = 20) -> list[dict]:
    """Tìm theo mã (vd. 'ND168_2024.D6.K9'), không phân biệt hoa thường."""
    with conn.cursor() as cur:
        cur.execute("""SELECT id, max(van_ban_id) AS van_ban_id, max(cap) AS cap, count(*) AS so_phien_ban,
                              (array_agg(noi_dung ORDER BY hieu_luc_tu DESC))[1] AS noi_dung
                       FROM don_vi WHERE id ILIKE %(p)s GROUP BY id
                       ORDER BY length(id), id LIMIT %(k)s""", {"p": prefix.replace("%", "") + "%", "k": limit})
        return _rows(cur)


def unit_summaries(conn, ids: list[str]) -> list[dict]:
    """Một dòng cho mỗi mã: nội dung mới nhất + số phiên bản (kết quả tìm kiếm, danh sách)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT id, max(van_ban_id) AS van_ban_id, max(cap) AS cap, count(*) AS so_phien_ban,
                              (array_agg(noi_dung ORDER BY hieu_luc_tu DESC))[1] AS noi_dung
                       FROM don_vi WHERE id = ANY(%(ids)s) GROUP BY id""", {"ids": ids})
        by = {r["id"]: r for r in _rows(cur)}
    return [by[i] for i in ids if i in by]


def amended_units(conn) -> list[dict]:
    """Các đơn vị có hơn một phiên bản hoặc do văn bản sửa đổi tạo ra (trang Lịch sử sửa đổi)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT id, max(van_ban_id) AS van_ban_id, max(cap) AS cap, count(*) AS so_phien_ban,
                              array_remove(array_agg(DISTINCT split_part(nguon_sua_doi, '.', 1)), NULL) AS van_ban_sua,
                              array_agg(DISTINCT loai_phien_ban) AS loai,
                              max(hieu_luc_tu) AS lan_sua_cuoi,
                              NOT bool_or(hieu_luc_den IS NULL) AS da_het_hieu_luc,
                              (array_agg(noi_dung ORDER BY hieu_luc_tu DESC))[1] AS noi_dung
                       FROM don_vi GROUP BY id
                       HAVING count(*) > 1 OR bool_or(nguon_sua_doi IS NOT NULL) OR bool_or(hieu_luc_den IS NOT NULL)
                       ORDER BY max(hieu_luc_tu) DESC, id""")
        return _rows(cur)


def overview(conn) -> dict:
    """Số liệu tổng quan (trang Thống kê, thanh bên)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT (SELECT count(*) FROM van_ban) AS van_ban,
                              count(DISTINCT id) AS don_vi, count(*) AS phien_ban,
                              count(*) FILTER (WHERE nguon_sua_doi IS NOT NULL) AS phien_ban_sua_doi,
                              count(embedding) AS co_embedding
                       FROM don_vi""")
        out = _rows(cur)[0]
        cur.execute("SELECT cap, count(DISTINCT id) AS n FROM don_vi GROUP BY cap")
        out["theo_cap"] = {r[0]: r[1] for r in cur.fetchall()}
    return out


# ---------- Nhật ký hỏi đáp (API /api/ask, /api/feedback, /api/admin/stats) ----------
def log_question(conn, cau_hoi: str, ngay: date, he_thong: str, tra_loi: str,
                 trich_dan: list[str], latency_ms: int) -> int:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO hoi_dap_log (cau_hoi, ngay_ap_dung, he_thong, tra_loi, trich_dan, latency_ms)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (cau_hoi, ngay, he_thong, tra_loi, trich_dan, latency_ms))
        log_id = cur.fetchone()[0]
    conn.commit()
    return log_id


def save_feedback(conn, log_id: int, danh_gia: int, ghi_chu: str | None) -> bool:
    with conn.cursor() as cur:
        cur.execute("UPDATE hoi_dap_log SET danh_gia = %s, ghi_chu = %s WHERE id = %s",
                    (danh_gia, ghi_chu, log_id))
        ok = cur.rowcount == 1
    conn.commit()
    return ok


def stats(conn, days: int = 30) -> dict:
    with conn.cursor() as cur:
        cur.execute("""SELECT thoi_gian::date AS ngay, count(*) AS so_cau, round(avg(latency_ms)) AS tb_ms
                       FROM hoi_dap_log WHERE thoi_gian > now() - make_interval(days => %s)
                       GROUP BY 1 ORDER BY 1""", (days,))
        theo_ngay = _rows(cur)
        cur.execute("""SELECT count(*) AS tong, count(*) FILTER (WHERE danh_gia = 1) AS huu_ich,
                              count(*) FILTER (WHERE danh_gia = -1) AS chua_dung
                       FROM hoi_dap_log""")
        tong = _rows(cur)[0]
        cur.execute("""SELECT round(avg(latency_ms)) AS tb_ms,
                              percentile_disc(0.5) WITHIN GROUP (ORDER BY latency_ms) AS trung_vi_ms,
                              round(avg(cardinality(trich_dan)), 1) AS tb_trich_dan
                       FROM hoi_dap_log""")
        tong.update(_rows(cur)[0])
        cur.execute("""SELECT id, thoi_gian, cau_hoi, tra_loi, ghi_chu FROM hoi_dap_log
                       WHERE danh_gia = -1 ORDER BY thoi_gian DESC LIMIT 20""")
        bi_danh_gia_sai = _rows(cur)
        cur.execute("""SELECT id, thoi_gian, cau_hoi, ngay_ap_dung, latency_ms, danh_gia,
                              cardinality(trich_dan) AS so_trich_dan
                       FROM hoi_dap_log ORDER BY thoi_gian DESC LIMIT 30""")
        gan_day = _rows(cur)
        cur.execute("""SELECT d AS ma, count(*) AS n FROM hoi_dap_log, unnest(trich_dan) AS d
                       GROUP BY d ORDER BY n DESC, d LIMIT 10""")
        hay_trich_dan = _rows(cur)
    return {"tong": tong, "theo_ngay": theo_ngay, "bi_danh_gia_sai": bi_danh_gia_sai,
            "gan_day": gan_day, "hay_trich_dan": hay_trich_dan}
