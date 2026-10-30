"""Truy cập Neo4j (local: Docker; cloud: AuraDB Free): nạp cấu trúc, quan hệ;
mở rộng đồ thị, lấy chuỗi phiên bản và đồ thị con để hiển thị.

Phụ trách: TV2 (nạp dữ liệu, đồ thị con), TV1 (truy vấn mở rộng).

Mỗi node là một MÃ ĐƠN VỊ (không phải phiên bản); nội dung và các phiên bản nằm trong PostgreSQL.
Mọi hàm nhận/trả mã đơn vị: đổi vid -> mã bằng graphrag.common.ids.base_id trước khi gọi.
Lược đồ đầy đủ: docs/thiet_ke_do_thi.md, mục 2–3.
"""
from __future__ import annotations

# Mở rộng theo cạnh nội dung, CẢ HAI chiều: chiều ngược của THAM_CHIEU mang về khoản trừ điểm, tước GPLX,
# biện pháp khắc phục ("Thực hiện hành vi quy định tại điểm b khoản 9 Điều này bị trừ 04 điểm").
# Không đi theo cạnh sửa đổi: phiên bản sau sửa đổi đã nằm sẵn dưới cùng mã trong PostgreSQL (fetch_valid).
CYPHER_EXPAND = """
MATCH (k:DonVi) WHERE k.id IN $seed_ids
OPTIONAL MATCH (k)-[:$edge_types*1..$hops]-(lq:DonVi)
RETURN collect(DISTINCT k.id) + collect(DISTINCT lq.id) AS ids
"""
# Lưu ý: Cypher không cho tham số hóa độ dài đường đi (*1..$hops) và loại cạnh;
# expand() thay $hops, $edge_types bằng giá trị đã kiểm tra trước khi chạy.
EDGE_TYPES = {"THAM_CHIEU", "HUONG_DAN", "THUOC"}

# Các đơn vị của văn bản sửa đổi đã tác động lên mã (để ghi "đã được … sửa đổi" và hiện lịch sử)
CYPHER_AMENDED_BY = """
MATCH (src:DonVi)-[r:SUA_DOI|THAY_THE|BO_SUNG|BAI_BO]->(n:DonVi) WHERE n.id IN $ids
RETURN n.id AS id, type(r) AS loai, src.id AS nguon, toString(r.ngay_hieu_luc) AS ngay_hieu_luc
ORDER BY ngay_hieu_luc
"""

CYPHER_NEIGHBORS = """
MATCH (n {id: $id})
OPTIONAL MATCH (n)-[r]-(m)
WITH n, r, m ORDER BY CASE type(r) WHEN 'THAM_CHIEU' THEN 0 WHEN 'SUA_DOI' THEN 1 WHEN 'THAY_THE' THEN 1
                                    WHEN 'BO_SUNG' THEN 1 WHEN 'BAI_BO' THEN 1 ELSE 2 END, m.id
WITH n, collect(DISTINCT {id: m.id, label: [l IN labels(m) WHERE l <> 'DonVi'][0], rel: type(r),
                          outgoing: startNode(r) = n}) AS nbs
RETURN n.id AS center, [l IN labels(n) WHERE l <> 'DonVi'][0] AS center_label, n.tieu_de AS center_tieu_de,
       size(nbs) AS total, nbs[0..$limit] AS neighbors
"""

# Đường đi từ seed tới các đơn vị lân cận (để chọn đơn vị mở rộng và vẽ đồ thị trong câu trả lời)
CYPHER_EXPAND_PATHS = """
MATCH (k:DonVi) WHERE k.id IN $seed_ids
MATCH p = (k)-[:$edge_types*1..$hops]-(m:DonVi)
WHERE NOT m:Chuong AND m.id <> k.id
RETURN k.id AS seed, m.id AS id, m.cap AS cap, length(p) AS hops,
       [r IN relationships(p) | {src: startNode(r).id, type: type(r), dst: endNode(r).id}] AS rels
"""


def connect(cfg: dict):
    from neo4j import GraphDatabase

    n = cfg["neo4j"]
    return GraphDatabase.driver(n["uri"], auth=(n["user"], n["password"]))


LABELS = {"Chuong", "Dieu", "Khoan", "Diem"}
REL_AMEND = {"SUA_DOI", "THAY_THE", "BO_SUNG", "BAI_BO"}


def apply_constraints(driver, cypher_text: str) -> None:
    """Chạy db/neo4j_constraints.cypher (bỏ dòng chú thích //)."""
    stmts = [x.strip() for x in "\n".join(l for l in cypher_text.splitlines() if not l.strip().startswith("//")).split(";")]
    with driver.session() as s:
        for st in stmts:
            if st:
                s.run(st)


def clear_graph(driver) -> None:
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")        # đồ thị vài nghìn node: xóa một lần là đủ


def load_structure(driver, versions: list[dict], van_ban: list[dict]) -> dict:
    """Một node cho mỗi mã đơn vị (nhãn theo cấp + nhãn chung DonVi), node VanBan từ manifest, cạnh THUOC con → cha.
    Thuộc tính node lấy từ phiên bản mới nhất: id, van_ban_id, cap, so, tieu_de."""
    nodes: dict[str, dict] = {}
    for r in versions:                      # phiên bản sau ghi đè phiên bản trước → giữ bản mới nhất
        nodes[r["id"]] = {"id": r["id"], "van_ban_id": r["van_ban_id"], "cap": r["cap"], "so": r["so"],
                          "tieu_de": r.get("tieu_de"), "parent": r.get("parent_id")}
    vb = [{"id": v["id"], "so_hieu": v["so_hieu"], "ten": v["ten"], "loai": v["loai"], "vai_tro": v["vai_tro"]}
          for v in van_ban]
    with driver.session() as s:
        s.run("UNWIND $rows AS r MERGE (v:VanBan {id: r.id}) SET v += r", rows=vb)
        for cap in LABELS:
            rows = [n for n in nodes.values() if n["cap"] == cap]
            s.run(f"UNWIND $rows AS r MERGE (n:DonVi:{cap} {{id: r.id}}) "
                  "SET n.van_ban_id = r.van_ban_id, n.cap = r.cap, n.so = r.so, n.tieu_de = r.tieu_de", rows=rows)
        doc_ids = {v["id"] for v in van_ban}
        to_unit = [{"c": n["id"], "p": n["parent"]} for n in nodes.values() if n["parent"] and n["parent"] not in doc_ids]
        to_doc = [{"c": n["id"], "p": n["parent"]} for n in nodes.values() if n["parent"] in doc_ids]
        s.run("UNWIND $rows AS r MATCH (c:DonVi {id: r.c}) MATCH (p:DonVi {id: r.p}) MERGE (c)-[:THUOC]->(p)",
              rows=to_unit)
        s.run("UNWIND $rows AS r MATCH (c:DonVi {id: r.c}) MATCH (p:VanBan {id: r.p}) MERGE (c)-[:THUOC]->(p)",
              rows=to_doc)
        # Văn bản sửa đổi → văn bản bị sửa (để trang Đồ thị hiện quan hệ giữa các văn bản)
        sd = [{"a": v["id"], "b": v["sua_doi_cho"]} for v in van_ban if v.get("sua_doi_cho")]
        s.run("UNWIND $rows AS r MATCH (a:VanBan {id: r.a}) MATCH (b:VanBan {id: r.b}) MERGE (a)-[:SUA_DOI]->(b)",
              rows=sd)
    return {"node_don_vi": len(nodes), "node_van_ban": len(vb)}


def load_relations(driver, refs: list[dict], amendments: list[dict]) -> dict:
    """refs: references.jsonl → (src)-[:THAM_CHIEU {text}]->(dst), bỏ dẫn chiếu ngoài kho / không tồn tại.
    amendments: amendments.jsonl → (nguon)-[:SUA_DOI|THAY_THE|BO_SUNG|BAI_BO {ngay_hieu_luc, pham_vi}]->(dich)."""
    ok_refs = [{"a": e["src"], "b": e["dst"], "text": e.get("text")} for e in refs
               if e.get("dst") and not e.get("khong_ton_tai")]
    out = {}
    with driver.session() as s:
        rec = s.run("UNWIND $rows AS r MATCH (a:DonVi {id: r.a}) MATCH (b:DonVi {id: r.b}) "
                    "MERGE (a)-[e:THAM_CHIEU]->(b) SET e.text = r.text RETURN count(e) AS n", rows=ok_refs).single()
        out["THAM_CHIEU"] = rec["n"]
        for loai in REL_AMEND:          # Cypher không tham số hóa được tên loại cạnh
            rows = [{"a": o["nguon"], "b": o["dich"], "ngay": o.get("ngay_hieu_luc"), "pham_vi": o.get("pham_vi")}
                    for o in amendments if o["loai"] == loai]
            rec = s.run(f"UNWIND $rows AS r MATCH (a:DonVi {{id: r.a}}) MATCH (b:DonVi {{id: r.b}}) "
                        f"MERGE (a)-[e:{loai}]->(b) SET e.ngay_hieu_luc = date(r.ngay), e.pham_vi = r.pham_vi "
                        "RETURN count(e) AS n", rows=rows).single()
            out[loai] = rec["n"]
    return out


def summary(driver) -> dict:
    with driver.session() as s:
        nodes = {r["nhan"]: r["n"] for r in s.run(
            "MATCH (n) UNWIND labels(n) AS nhan WITH nhan WHERE nhan <> 'DonVi' RETURN nhan, count(*) AS n")}
        rels = {r["loai"]: r["n"] for r in s.run("MATCH ()-[r]->() RETURN type(r) AS loai, count(*) AS n")}
        ids = [r["id"] for r in s.run("MATCH (n:DonVi) RETURN n.id AS id")]
    return {"node": nodes, "canh": rels, "ids": ids}


def expand(driver, seed_ids: list[str], hops: int = 1,
           edge_types: list[str] | tuple[str, ...] = ("THAM_CHIEU", "HUONG_DAN", "THUOC")) -> list[str]:
    """seed_ids: mã đơn vị. Trả về mã các đơn vị liên quan (gồm cả seed), chưa lọc theo ngày."""
    if not set(edge_types) <= EDGE_TYPES:
        raise ValueError(f"loại cạnh không hợp lệ: {edge_types}")
    query = CYPHER_EXPAND.replace("$hops", str(int(hops))).replace("$edge_types", "|".join(edge_types))
    with driver.session() as s:
        rec = s.run(query, seed_ids=seed_ids).single()
        return [i for i in (rec["ids"] if rec else []) if i]


def expand_paths(driver, seed_ids: list[str], hops: int = 1,
                 edge_types: list[str] | tuple[str, ...] = ("THAM_CHIEU", "HUONG_DAN", "THUOC")) -> list[dict]:
    """Như expand() nhưng trả về từng đường đi: [{seed, id, cap, hops, rels: [{src, type, dst}]}].
    Dùng trong graph_rag để ưu tiên đơn vị theo loại cạnh và để vẽ đồ thị cho người dùng thấy vì sao có đơn vị đó."""
    if not set(edge_types) <= EDGE_TYPES:
        raise ValueError(f"loại cạnh không hợp lệ: {edge_types}")
    if not seed_ids:
        return []
    query = CYPHER_EXPAND_PATHS.replace("$hops", str(int(hops))).replace("$edge_types", "|".join(edge_types))
    with driver.session() as s:
        return [dict(r) for r in s.run(query, seed_ids=seed_ids)]


def graph_counts(driver) -> dict:
    """Số node, cạnh theo loại (trang Thống kê)."""
    with driver.session() as s:
        nodes = {r["nhan"]: r["n"] for r in s.run(
            "MATCH (n) UNWIND labels(n) AS nhan WITH nhan WHERE nhan <> 'DonVi' RETURN nhan, count(*) AS n")}
        rels = {r["loai"]: r["n"] for r in s.run("MATCH ()-[r]->() RETURN type(r) AS loai, count(*) AS n")}
    return {"node": nodes, "canh": rels, "tong_node": sum(nodes.values()), "tong_canh": sum(rels.values())}


def amended_by(driver, ids: list[str]) -> list[dict]:
    """[{id, loai, nguon, ngay_hieu_luc}]: văn bản sửa đổi nào đã sửa/bổ sung/thay thế/bãi bỏ các mã này."""
    with driver.session() as s:
        return [dict(r) for r in s.run(CYPHER_AMENDED_BY, ids=ids)]


def neighbors(driver, uid: str, limit: int = 60) -> dict | None:
    """Đồ thị con 1 bước quanh `uid` để giao diện vẽ (trang Khám phá đồ thị).
    Ưu tiên cạnh dẫn chiếu, rồi cạnh sửa đổi, rồi cạnh cấu trúc; tối đa `limit` node lân cận."""
    with driver.session() as s:
        rec = s.run(CYPHER_NEIGHBORS, id=uid, limit=int(limit)).single()
    if not rec or rec["center"] is None:
        return None
    nbs = [x for x in rec["neighbors"] if x["id"]]
    return {"center": {"id": rec["center"], "label": rec["center_label"], "tieu_de": rec["center_tieu_de"]},
            "neighbors": nbs, "total": rec["total"]}
