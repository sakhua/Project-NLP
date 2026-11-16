"""Lưu và truy vấn chỉ mục GraphRAG kiểu Microsoft (baseline B2) trong PostgreSQL (+ bản sao để xem trên Neo4j).

Bảng: db/ms_graphrag.sql. Ghi bởi scripts/05_ms_graphrag_index.py; đọc bởi graphrag/pipeline/ms_graphrag.py.
"""
from __future__ import annotations

from graphrag.storage.postgres import _rows

BANG = ["ms_thanh_vien", "ms_cong_dong", "ms_lien_ket", "ms_quan_he", "ms_thuc_the"]


# ---------------------------------------------------------------- ghi
def tao_bang(conn, schema_sql: str) -> None:
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()


def nap(conn, thuc_the: list[dict], quan_he: list[dict], cong_dong: list[dict],
        emb_tt: dict[str, list[float]], emb_cd: dict[str, list[float]]) -> dict:
    """Xóa chỉ mục cũ rồi nạp lại toàn bộ."""
    with conn.cursor() as cur:
        for b in BANG:
            cur.execute(f"TRUNCATE {b}")
        cur.executemany(
            "INSERT INTO ms_thuc_the (id, ten, loai, mo_ta, tan_suat, bac, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            [(e["id"], e["ten"], e["loai"], e["mo_ta"], e["tan_suat"], e["bac"], emb_tt.get(e["id"])) for e in thuc_the])
        cur.executemany("INSERT INTO ms_quan_he (nguon, dich, mo_ta, trong_so, tan_suat) VALUES (%s,%s,%s,%s,%s) "
                        "ON CONFLICT DO NOTHING",
                        [(r["nguon"], r["dich"], r["mo_ta"], r["trong_so"], r["tan_suat"]) for r in quan_he])
        cur.executemany("INSERT INTO ms_lien_ket (thuc_the_id, vid, don_vi_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                        [(e["id"], v, v.split("@")[0]) for e in thuc_the for v in e["vids"]])
        cur.executemany(
            "INSERT INTO ms_cong_dong (id, cap, cha, so_thanh_vien, tieu_de, tom_tat, bao_cao, muc_do, embedding) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [(c["id"], c["cap"], c["cha"], len(c["thanh_vien"]), c["tieu_de"], c["tom_tat"], c["bao_cao"], c["muc_do"],
              emb_cd.get(c["id"])) for c in cong_dong])
        cur.executemany("INSERT INTO ms_thanh_vien (cong_dong_id, thuc_the_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        [(c["id"], t) for c in cong_dong for t in c["thanh_vien"]])
    conn.commit()
    return dem(conn)


def dem(conn) -> dict:
    out = {}
    with conn.cursor() as cur:
        for b in BANG:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (b,))
            if not cur.fetchone()[0]:
                out[b] = 0
                continue
            cur.execute(f"SELECT count(*) FROM {b}")
            out[b] = cur.fetchone()[0]
    return out


# ---------------------------------------------------------------- đọc (truy vấn)
def tim_thuc_the(conn, qvec, k: int = 10) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""SELECT id, ten, loai, mo_ta, bac, 1 - (embedding <=> %(q)s::vector) AS diem
                       FROM ms_thuc_the WHERE embedding IS NOT NULL
                       ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s""", {"q": qvec, "k": k})
        return _rows(cur)


def lay_thuc_the(conn, ids: list[str]) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, ten, loai, mo_ta, bac FROM ms_thuc_the WHERE id = ANY(%s)", (ids,))
        return _rows(cur)


def quan_he_cua(conn, ids: list[str], limit: int = 200) -> list[dict]:
    """Quan hệ có ít nhất một đầu thuộc ids, trọng số giảm dần."""
    with conn.cursor() as cur:
        cur.execute("""SELECT nguon, dich, mo_ta, trong_so, tan_suat FROM ms_quan_he
                       WHERE nguon = ANY(%(ids)s) OR dich = ANY(%(ids)s)
                       ORDER BY trong_so DESC LIMIT %(n)s""", {"ids": ids, "n": limit})
        return _rows(cur)


def cong_dong_cua(conn, ids: list[str], limit: int = 20) -> list[dict]:
    """Cộng đồng chứa các thực thể ids, xếp theo số thực thể khớp, mức độ quan trọng, cấp sâu hơn (cụ thể hơn)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT c.id, c.cap, c.tieu_de, c.tom_tat, c.bao_cao, c.muc_do, c.so_thanh_vien,
                              count(*) AS so_khop
                       FROM ms_thanh_vien t JOIN ms_cong_dong c ON c.id = t.cong_dong_id
                       WHERE t.thuc_the_id = ANY(%(ids)s) AND c.tieu_de <> ''
                       GROUP BY c.id ORDER BY so_khop DESC, c.muc_do DESC NULLS LAST, c.cap DESC LIMIT %(n)s""",
                    {"ids": ids, "n": limit})
        return _rows(cur)


def don_vi_cua(conn, ids: list[str]) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT thuc_the_id, vid, don_vi_id FROM ms_lien_ket WHERE thuc_the_id = ANY(%s)", (ids,))
        return _rows(cur)


def cong_dong_cho_global(conn, qvec, cap: int = 0, k: int = 24) -> list[dict]:
    """Global search: cộng đồng ở một cấp, xếp theo độ gần câu hỏi × mức độ quan trọng (lọc trước để giảm chi phí map)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT id, cap, tieu_de, tom_tat, bao_cao, muc_do, so_thanh_vien,
                              1 - (embedding <=> %(q)s::vector) AS gan
                       FROM ms_cong_dong WHERE cap = %(cap)s AND embedding IS NOT NULL AND tieu_de <> ''
                       ORDER BY (1 - (embedding <=> %(q)s::vector)) * (0.5 + coalesce(muc_do, 5) / 20) DESC
                       LIMIT %(k)s""", {"q": qvec, "cap": cap, "k": k})
        return _rows(cur)


# ---------------------------------------------------------------- Neo4j (chỉ để xem trực quan)
def nap_neo4j(driver, thuc_the: list[dict], quan_he: list[dict], cong_dong: list[dict]) -> dict:
    """Node :ThucThe, :CongDong; cạnh LIEN_QUAN (thực thể–thực thể), XUAT_HIEN_TAI (thực thể → node điều khoản),
    THANH_VIEN (thực thể → cộng đồng), CON_CUA (cộng đồng con → cha). Không đụng tới đồ thị văn bản."""
    with driver.session() as s:
        s.run("MATCH (n) WHERE n:ThucThe OR n:CongDong DETACH DELETE n")
        s.run("CREATE CONSTRAINT thuc_the_id IF NOT EXISTS FOR (n:ThucThe) REQUIRE n.id IS UNIQUE")
        s.run("CREATE CONSTRAINT cong_dong_id IF NOT EXISTS FOR (n:CongDong) REQUIRE n.id IS UNIQUE")
        for i in range(0, len(thuc_the), 1000):
            s.run("UNWIND $rows AS r CREATE (:ThucThe {id: r.id, ten: r.ten, loai: r.loai, mo_ta: r.mo_ta})",
                  rows=[{k: e[k] for k in ("id", "ten", "loai", "mo_ta")} for e in thuc_the[i:i + 1000]])
        for i in range(0, len(quan_he), 1000):
            s.run("""UNWIND $rows AS r MATCH (a:ThucThe {id: r.nguon}), (b:ThucThe {id: r.dich})
                     CREATE (a)-[:LIEN_QUAN {mo_ta: r.mo_ta, trong_so: r.trong_so}]->(b)""",
                  rows=[{k: r[k] for k in ("nguon", "dich", "mo_ta", "trong_so")} for r in quan_he[i:i + 1000]])
        lk = [{"t": e["id"], "u": u} for e in thuc_the for u in e["don_vi"]]
        for i in range(0, len(lk), 2000):
            s.run("""UNWIND $rows AS r MATCH (a:ThucThe {id: r.t}), (u:DonVi {id: r.u})
                     MERGE (a)-[:XUAT_HIEN_TAI]->(u)""", rows=lk[i:i + 2000])
        s.run("UNWIND $rows AS r CREATE (:CongDong {id: r.id, cap: r.cap, tieu_de: r.tieu_de, tom_tat: r.tom_tat})",
              rows=[{k: c[k] for k in ("id", "cap", "tieu_de", "tom_tat")} for c in cong_dong])
        s.run("""UNWIND $rows AS r MATCH (c:CongDong {id: r.id}), (p:CongDong {id: r.cha}) CREATE (c)-[:CON_CUA]->(p)""",
              rows=[{"id": c["id"], "cha": c["cha"]} for c in cong_dong if c["cha"]])
        tv = [{"c": c["id"], "t": t} for c in cong_dong for t in c["thanh_vien"]]
        for i in range(0, len(tv), 2000):
            s.run("""UNWIND $rows AS r MATCH (a:ThucThe {id: r.t}), (c:CongDong {id: r.c})
                     CREATE (a)-[:THANH_VIEN]->(c)""", rows=tv[i:i + 2000])
        c1 = s.run("MATCH (n:ThucThe) RETURN count(n) AS c").single()["c"]
        c2 = s.run("MATCH (n:CongDong) RETURN count(n) AS c").single()["c"]
        c3 = s.run("MATCH (:ThucThe)-[r:XUAT_HIEN_TAI]->(:DonVi) RETURN count(r) AS c").single()["c"]
    return {"ThucThe": c1, "CongDong": c2, "XUAT_HIEN_TAI": c3}
