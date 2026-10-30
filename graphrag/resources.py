"""Gom mọi tài nguyên dùng chung (kết nối DB, mô hình, chỉ mục BM25) vào một đối tượng.

- Backend tạo MỘT Resources khi khởi động và dùng cho mọi request.
- Script chạy đánh giá (môn NLP) cũng dùng được: Resources(load_config("local")).
- Mọi thứ được tạo khi dùng lần đầu (lazy), nên backend vẫn khởi động được
  dù chưa cấu hình xong DB (hữu ích ở bước "Hello cloud").
"""
from __future__ import annotations

import threading
from functools import cached_property


class Resources:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._lock = threading.Lock()

    @cached_property
    def pg_pool(self):
        from graphrag.storage.postgres import make_pool

        with self._lock:
            return make_pool(self.cfg)

    @cached_property
    def neo4j(self):
        from graphrag.storage.neo4j_store import connect

        with self._lock:
            return connect(self.cfg)

    @cached_property
    def embedder(self):
        from graphrag.embedding import get_embedder

        return get_embedder(self.cfg)

    @cached_property
    def llm(self):
        from graphrag.llm import get_llm

        return get_llm(self.cfg)

    @cached_property
    def bm25(self):
        """Dựng chỉ mục BM25 từ bảng don_vi (vài nghìn phiên bản, mất vài giây). search() trả về vid."""
        from graphrag.retrieval.bm25 import BM25Index
        from graphrag.storage.postgres import all_unit_texts

        with self.pg_pool.connection() as conn:
            ids, texts = all_unit_texts(conn)
        return BM25Index(ids, texts)

    def check(self) -> dict:
        """Kiểm tra kết nối tới PostgreSQL và Neo4j (dùng cho /health/db)."""
        out = {}
        try:
            with self.pg_pool.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM don_vi")
                out["postgres"] = {"ok": True, "don_vi": cur.fetchone()[0]}
        except Exception as e:  # noqa: BLE001
            out["postgres"] = {"ok": False, "error": type(e).__name__}
        try:
            self.neo4j.verify_connectivity()
            with self.neo4j.session() as s:
                out["neo4j"] = {"ok": True, "nodes": s.run("MATCH (n) RETURN count(n) AS c").single()["c"]}
        except Exception as e:  # noqa: BLE001
            out["neo4j"] = {"ok": False, "error": type(e).__name__}
        return out

    def close(self) -> None:
        if "pg_pool" in self.__dict__:
            self.pg_pool.close()
        if "neo4j" in self.__dict__:
            self.neo4j.close()
