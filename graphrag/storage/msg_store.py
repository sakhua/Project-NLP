"""Lưu và truy vấn chỉ mục B2 theo GraphRAG GỐC (bảng msg_*, db/ms_graphrag_goc.sql).

Ghi bởi scripts/05_ms_graphrag_index.py --ban goc; đọc bởi graphrag/pipeline/ms_graphrag_goc.py.
"""
from __future__ import annotations

from graphrag.storage.postgres import _rows

BANG = ["msg_thanh_vien", "msg_cong_dong", "msg_lien_ket", "msg_quan_he", "msg_thuc_the", "msg_text_unit"]


def tao_bang(conn, schema_sql: str) -> None:
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()


def nap(conn, text_units: list[dict], thuc_the: list[dict], quan_he: list[dict], cong_dong: list[dict],
        emb_tt: dict, emb_cd: dict) -> dict:
    """Xóa chỉ mục cũ rồi nạp lại toàn bộ."""
    with conn.cursor() as cur:
        for b in BANG:
            cur.execute(f"TRUNCATE {b}")
        cur.executemany("INSERT INTO msg_text_unit (ma_ngan, vid, don_vi_id) VALUES (%s,%s,%s)",
                        [(u["ma_ngan"], u["vid"], u["id"]) for u in text_units])
        cur.executemany(
            "INSERT INTO msg_thuc_the (id, ten, loai, mo_ta, tan_suat, bac, ma_ngan, embedding) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            [(e["id"], e["ten"], e["loai"], e["mo_ta"], e["tan_suat"], e["bac"], e["ma_ngan"], emb_tt.get(e["id"]))
             for e in thuc_the])
        cur.executemany(
            "INSERT INTO msg_quan_he (nguon, dich, mo_ta, trong_so, tan_suat, bac_ket_hop, ma_ngan, vids) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            [(r["nguon"], r["dich"], r["mo_ta"], r["trong_so"], r["tan_suat"], r["bac_ket_hop"], r["ma_ngan"],
              r["vids"]) for r in quan_he])
        cur.executemany("INSERT INTO msg_lien_ket (thuc_the_id, vid, don_vi_id) VALUES (%s,%s,%s) "
                        "ON CONFLICT DO NOTHING",
                        [(e["id"], v, v.split("@")[0]) for e in thuc_the for v in e["vids"]])
        cur.executemany(
            "INSERT INTO msg_cong_dong (id, cap, cha, so_thanh_vien, tieu_de, tom_tat, bao_cao, muc_do, embedding) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [(c["id"], c["cap"], c["cha"], len(c["thanh_vien"]), c["tieu_de"], c["tom_tat"], c["bao_cao"],
              c["muc_do"], emb_cd.get(c["id"])) for c in cong_dong])
        cur.executemany("INSERT INTO msg_thanh_vien (cong_dong_id, thuc_the_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        [(c["id"], t) for c in cong_dong for t in c["thanh_vien"]])
    conn.commit()
    return dem(conn)


def dem(conn, ten_cu: bool = False) -> dict:
    """Số dòng mỗi bảng. ten_cu=True: đổi khóa về ms_* để giao diện (trang Thống kê) đọc như bản cũ."""
    out = {}
    with conn.cursor() as cur:
        for b in BANG:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (b,))
            n = 0
            if cur.fetchone()[0]:
                cur.execute(f"SELECT count(*) FROM {b}")
                n = cur.fetchone()[0]
            out[b.replace("msg_", "ms_") if ten_cu else b] = n
    return out


# ---------------------------------------------------------------- truy vấn (local search)
def tim_thuc_the(conn, qvec, k: int = 20) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""SELECT id, ten, loai, mo_ta, bac, ma_ngan, 1 - (embedding <=> %(q)s::vector) AS diem
                       FROM msg_thuc_the WHERE embedding IS NOT NULL
                       ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s""", {"q": qvec, "k": k})
        return _rows(cur)


def quan_he_cua(conn, ids: list[str]) -> list[dict]:
    """Mọi quan hệ có ít nhất một đầu thuộc ids (để chia trong nhóm / ra ngoài và đếm quan hệ theo text unit)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT nguon, dich, mo_ta, trong_so, tan_suat, bac_ket_hop, ma_ngan, vids FROM msg_quan_he
                       WHERE nguon = ANY(%(ids)s) OR dich = ANY(%(ids)s)""", {"ids": ids})
        return _rows(cur)


def ten_thuc_the(conn, ids: list[str]) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, ten FROM msg_thuc_the WHERE id = ANY(%s)", (ids,))
        return {r[0]: r[1] for r in cur.fetchall()}


def cong_dong_chua(conn, ids: list[str]) -> list[dict]:
    """Mọi cộng đồng (mọi cấp) chứa ít nhất một thực thể trong ids, kèm số thực thể khớp."""
    with conn.cursor() as cur:
        cur.execute("""SELECT c.id, c.cap, c.tieu_de, c.tom_tat, c.bao_cao, c.muc_do, c.so_thanh_vien,
                              count(*) AS so_khop
                       FROM msg_thanh_vien t JOIN msg_cong_dong c ON c.id = t.cong_dong_id
                       WHERE t.thuc_the_id = ANY(%(ids)s) AND c.tieu_de <> ''
                       GROUP BY c.id""", {"ids": ids})
        return _rows(cur)


def text_unit_cua(conn, ids: list[str]) -> list[dict]:
    """(thực thể, text unit) kèm id ngắn của text unit."""
    with conn.cursor() as cur:
        cur.execute("""SELECT l.thuc_the_id, l.vid, l.don_vi_id, u.ma_ngan
                       FROM msg_lien_ket l JOIN msg_text_unit u ON u.vid = l.vid
                       WHERE l.thuc_the_id = ANY(%s)""", (ids,))
        return _rows(cur)


def phien_ban(conn, vids: list[str]) -> dict[str, dict]:
    """Nội dung các phiên bản điều khoản theo vid (bản gốc không lọc theo ngày: dùng đúng phiên bản đã trích)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT vid, id, van_ban_id, cap, tieu_de, noi_dung, ngu_canh, hieu_luc_tu, hieu_luc_den,
                              nguon_sua_doi, loai_phien_ban
                       FROM don_vi WHERE vid = ANY(%s)""", (vids,))
        return {r["vid"]: r for r in _rows(cur)}


def cong_dong_cho_global(conn, qvec, cap: int = 0, k: int = 24) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""SELECT id, cap, tieu_de, tom_tat, bao_cao, muc_do, so_thanh_vien,
                              1 - (embedding <=> %(q)s::vector) AS gan
                       FROM msg_cong_dong WHERE cap = %(cap)s AND embedding IS NOT NULL AND tieu_de <> ''
                       ORDER BY (1 - (embedding <=> %(q)s::vector)) * (0.5 + coalesce(muc_do, 5) / 20) DESC
                       LIMIT %(k)s""", {"q": qvec, "cap": cap, "k": k})
        return _rows(cur)
