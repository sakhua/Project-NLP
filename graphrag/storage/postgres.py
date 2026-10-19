"""Truy cập PostgreSQL + pgvector (local: Docker; cloud: Supabase).

Phụ trách: TV2 (ghi dữ liệu, truy vấn tra cứu), TV3 (tìm vector).
Mọi hàm nhận `conn` là một kết nối psycopg (lấy từ Resources.pg_pool.connection()).
"""
from __future__ import annotations

from datetime import date

VECTOR_COLUMNS = {"embedding"}   # chỉ cho phép tên cột này trong SQL (tránh SQL injection)

SQL_VECTOR_SEARCH = """
SELECT id, 1 - ({col} <=> %(qvec)s::vector) AS score
FROM don_vi
WHERE cap IN ('Khoan', 'Diem', 'Dieu') AND {col} IS NOT NULL
ORDER BY {col} <=> %(qvec)s::vector
LIMIT %(k)s;
"""

SQL_VALID = "hieu_luc_tu <= %(ngay)s AND (hieu_luc_den IS NULL OR %(ngay)s < hieu_luc_den)"

SQL_FETCH_VALID = f"""
SELECT id, van_ban_id, cap, tieu_de, noi_dung, hieu_luc_tu, hieu_luc_den
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
    register_vector(conn)
    return conn


def _rows(cur) -> list[dict]:
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------- Ghi dữ liệu (scripts/04_load.py) ----------
def upsert_van_ban(conn, rows: list[dict]) -> None:
    # TODO(TV2): INSERT ... ON CONFLICT (id) DO UPDATE
    raise NotImplementedError


def upsert_don_vi(conn, rows: list[dict]) -> None:
    # TODO(TV2): ghi nội dung + hiệu lực + thứ tự; embedding ghi bằng update_embeddings
    raise NotImplementedError


def update_embeddings(conn, ids: list[str], vectors, column: str = "embedding") -> None:
    # TODO(TV2): UPDATE don_vi SET {column} = %s WHERE id = %s  (executemany)
    assert column in VECTOR_COLUMNS
    raise NotImplementedError


# ---------- Truy xuất (pipeline) ----------
def all_unit_texts(conn) -> tuple[list[str], list[str]]:
    """(ids, nội dung) của mọi Điều/Khoản/Điểm, để dựng chỉ mục BM25 khi khởi động."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, coalesce(ngu_canh || E'\\n', '') || noi_dung FROM don_vi "
                    "WHERE cap IN ('Khoan','Diem','Dieu') ORDER BY id")
        rows = cur.fetchall()
    return [r[0] for r in rows], [r[1] for r in rows]


def vector_search(conn, qvec, k: int = 50, column: str = "embedding") -> list[tuple[str, float]]:
    if column not in VECTOR_COLUMNS:
        raise ValueError(column)
    with conn.cursor() as cur:
        cur.execute(SQL_VECTOR_SEARCH.format(col=column), {"qvec": qvec, "k": k})
        return [(r[0], float(r[1])) for r in cur.fetchall()]


def fetch_valid(conn, ids: list[str], ngay: date) -> list[dict]:
    """Lấy nội dung các đơn vị và chỉ giữ phiên bản có hiệu lực tại `ngay`."""
    with conn.cursor() as cur:
        cur.execute(SQL_FETCH_VALID, {"ids": ids, "ngay": ngay})
        return _rows(cur)


# ---------- Tra cứu (API /api/documents, /api/units) ----------
def list_van_ban(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""SELECT id, so_hieu, ten, loai, co_quan, ngay_ban_hanh, hieu_luc_tu, vai_tro, sua_doi_cho
                       FROM van_ban ORDER BY hieu_luc_tu DESC NULLS LAST, id""")
        return _rows(cur)


def list_units_valid(conn, van_ban_id: str, ngay: date) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(f"""SELECT id, cap, parent_id, so, tieu_de, noi_dung, hieu_luc_tu, hieu_luc_den
                        FROM don_vi WHERE van_ban_id = %(vb)s AND {SQL_VALID}
                        ORDER BY thu_tu NULLS LAST, id""", {"vb": van_ban_id, "ngay": ngay})
        return _rows(cur)


def get_units(conn, ids: list[str]) -> list[dict]:
    """Mọi phiên bản (không lọc ngày) – để hiển thị lịch sử sửa đổi."""
    with conn.cursor() as cur:
        cur.execute("""SELECT id, van_ban_id, cap, tieu_de, noi_dung, hieu_luc_tu, hieu_luc_den
                       FROM don_vi WHERE id = ANY(%(ids)s) ORDER BY hieu_luc_tu""", {"ids": ids})
        return _rows(cur)


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
        cur.execute("""SELECT id, thoi_gian, cau_hoi, tra_loi, ghi_chu FROM hoi_dap_log
                       WHERE danh_gia = -1 ORDER BY thoi_gian DESC LIMIT 20""")
        bi_danh_gia_sai = _rows(cur)
    return {"tong": tong, "theo_ngay": theo_ngay, "bi_danh_gia_sai": bi_danh_gia_sai}
