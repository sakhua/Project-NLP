"""Truy cập Neo4j (local: Docker; cloud: AuraDB Free): nạp cấu trúc, quan hệ;
mở rộng đồ thị, lấy chuỗi phiên bản và đồ thị con để hiển thị.

Phụ trách: TV2 (nạp dữ liệu, đồ thị con), TV1 (truy vấn mở rộng).
"""
from __future__ import annotations

CYPHER_EXPAND = """
MATCH (k) WHERE k.id IN $seed_ids
OPTIONAL MATCH (k)-[:THAM_CHIEU|HUONG_DAN|THUOC*1..$hops]-(lq)
WITH collect(DISTINCT k) + collect(DISTINCT lq) AS ds
UNWIND ds AS n
OPTIONAL MATCH (n)-[:SUA_DOI|BO_SUNG|THAY_THE*0..3]-(pb)
RETURN collect(DISTINCT n.id) + collect(DISTINCT pb.id) AS ids
"""
# Lưu ý: Cypher không cho tham số hóa độ dài đường đi (*1..$hops);
# expand() bên dưới thay $hops bằng số nguyên trước khi chạy.

CYPHER_VERSIONS = """
MATCH (n {id: $id})
OPTIONAL MATCH (n)-[:SUA_DOI|BO_SUNG|THAY_THE|BAI_BO*1..3]-(pb)
RETURN collect(DISTINCT pb.id) AS ids
"""

CYPHER_NEIGHBORS = """
MATCH (n {id: $id})
OPTIONAL MATCH (n)-[r]-(m)
RETURN n.id AS center, labels(n)[0] AS center_label,
       collect(DISTINCT {id: m.id, label: labels(m)[0], rel: type(r),
                         outgoing: startNode(r) = n}) AS neighbors
"""


def connect(cfg: dict):
    from neo4j import GraphDatabase

    n = cfg["neo4j"]
    return GraphDatabase.driver(n["uri"], auth=(n["user"], n["password"]))


def load_structure(driver, units: list[dict]) -> None:
    # TODO(TV2): MERGE node theo nhãn cấp (VanBan/Chuong/Dieu/Khoan/Diem) và cạnh THUOC
    raise NotImplementedError


def load_relations(driver, refs: list[dict], amendments: list[dict]) -> None:
    # TODO(TV2): cạnh THAM_CHIEU, HUONG_DAN, SUA_DOI/BO_SUNG/THAY_THE/BAI_BO (kèm ngay_hieu_luc)
    raise NotImplementedError


def expand(driver, seed_ids: list[str], hops: int = 1) -> list[str]:
    """Trả về mã các đơn vị liên quan và mọi phiên bản của chúng."""
    query = CYPHER_EXPAND.replace("$hops", str(int(hops)))
    with driver.session() as s:
        rec = s.run(query, seed_ids=seed_ids).single()
        return [i for i in (rec["ids"] if rec else []) if i]


def versions(driver, uid: str) -> list[str]:
    """Mã các văn bản/đơn vị sửa đổi, bổ sung, thay thế, bãi bỏ liên quan tới `uid`."""
    with driver.session() as s:
        rec = s.run(CYPHER_VERSIONS, id=uid).single()
        return [i for i in (rec["ids"] if rec else []) if i]


def neighbors(driver, uid: str) -> dict | None:
    """Đồ thị con 1 bước quanh `uid` để giao diện vẽ (trang Đồ thị)."""
    with driver.session() as s:
        rec = s.run(CYPHER_NEIGHBORS, id=uid).single()
    if not rec:
        return None
    nbs = [x for x in rec["neighbors"] if x["id"]]
    return {"center": {"id": rec["center"], "label": rec["center_label"]}, "neighbors": nbs}
