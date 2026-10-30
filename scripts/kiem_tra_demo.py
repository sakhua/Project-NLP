"""Chạy thử toàn bộ câu hỏi demo (data/demo/cau_hoi_demo.json) qua pipeline GraphRAG thật trước buổi demo.

Cần: Docker đã bật (PostgreSQL + Neo4j đã nạp dữ liệu), OPENROUTER_API_KEY trong .env.
Chạy:   python scripts/kiem_tra_demo.py              # mọi câu
        python scripts/kiem_tra_demo.py D1 D6        # vài câu
Kết quả: in bảng ĐẠT/XEM LẠI ra màn hình và ghi chi tiết vào data/demo/ket_qua_chay_thu.md
  ĐẠT     = có đủ mã cần trích dẫn, mã cần có trong ngữ cảnh và các cụm từ trong đáp án.
  XEM LẠI = thiếu một trong các điều trên: đọc câu trả lời trong file kết quả, sửa câu hỏi hoặc bỏ khỏi kịch bản.
Chi phí: khoảng 11 lượt gọi gpt-4o-mini + embedding + rerank (dưới 0,05 USD).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from graphrag.common.config import load_config  # noqa: E402
from graphrag.pipeline import graph_rag  # noqa: E402
from graphrag.resources import Resources  # noqa: E402


def main() -> None:
    items = json.loads((ROOT / "data/demo/cau_hoi_demo.json").read_text(encoding="utf-8"))
    chon = set(sys.argv[1:])
    res = Resources(load_config())
    print("Kiểm tra kết nối PostgreSQL, Neo4j…")
    st = res.check()
    if not st["postgres"]["ok"] or not st["neo4j"]["ok"]:
        print(f"  PostgreSQL: {st['postgres']}\n  Neo4j: {st['neo4j']}")
        sys.exit("Chưa kết nối được cơ sở dữ liệu. Mở Docker Desktop rồi chạy:\n"
                 "  docker compose -f db/docker-compose.yml --env-file .env up -d\n"
                 "đợi khoảng 30 giây (Neo4j khởi động chậm) rồi chạy lại script này.")
    print("Dựng chỉ mục BM25…")
    _ = res.bm25
    answers: dict[str, dict] = {}
    rows, md = [], ["# Kết quả chạy thử câu hỏi demo", "", f"Chạy lúc {time.strftime('%d/%m/%Y %H:%M')}", ""]
    for it in items:
        if chon and it["id"] not in chon and not any(x.get("tiep_theo") == it["id"] for x in items if x["id"] in chon):
            continue
        ngay = date.fromisoformat(it["ngay"]) if it.get("ngay") else date.today()
        history = []
        if it.get("tiep_theo") and it["tiep_theo"] in answers:
            prev = next(x for x in items if x["id"] == it["tiep_theo"])
            history = [{"role": "user", "content": prev["cau_hoi"]},
                       {"role": "assistant", "content": answers[it["tiep_theo"]]["answer"]}]
        t0 = time.perf_counter()
        try:
            out = graph_rag.answer(res, it["cau_hoi"], ngay=ngay, history=history)
        except Exception as e:  # noqa: BLE001
            rows.append((it["id"], "LỖI", f"{type(e).__name__}: {e}"[:80]))
            continue
        answers[it["id"]] = out
        ctx = {u["id"] for u in out["units"]}
        thieu_td = [x for x in it["can_trich_dan"] if x not in out["citations"]]
        thieu_nc = [x for x in it["can_co_trong_ngu_canh"] if x not in ctx]
        thieu_tu = [x for x in it["dap_an_co"] if x.lower() not in out["answer"].lower()]
        ok = not (thieu_td or thieu_nc or thieu_tu)
        ly_do = "; ".join(filter(None, [
            f"thiếu trích dẫn {thieu_td}" if thieu_td else "", f"ngữ cảnh thiếu {thieu_nc}" if thieu_nc else "",
            f"thiếu cụm {thieu_tu}" if thieu_tu else ""]))
        rows.append((it["id"], "ĐẠT" if ok else "XEM LẠI", f"{time.perf_counter() - t0:.1f}s " + ly_do))
        md += [f"## {it['id']}. {it['nhom']} {'✅' if ok else '⚠️'}", "",
               f"**Câu hỏi** ({ngay.strftime('%d/%m/%Y')}): {it['cau_hoi']}", ""]
        if out.get("question_rewritten"):
            md += [f"**Hiểu là:** {out['question_rewritten']}", ""]
        md += ["**Câu trả lời của hệ thống:**", "", out["answer"], "",
               f"**Đáp án đúng (đối chiếu):** {it['dap_an_dung']}", "",
               f"Trích dẫn: {', '.join(out['citations']) or '(không có)'} · "
               f"ngữ cảnh {len(out['units'])} điều khoản ({sum(u['origin'] == 'graph' for u in out['units'])} từ đồ thị) · "
               f"{out['latency_s']} giây" + (f" · **{ly_do}**" if ly_do else ""), ""]
    res.close()
    print(f"\n{'Câu':<5}{'Kết quả':<10}Ghi chú")
    for r in rows:
        print(f"{r[0]:<5}{r[1]:<10}{r[2]}")
    p = ROOT / "data/demo/ket_qua_chay_thu.md"
    p.write_text("\n".join(md), encoding="utf-8")
    print(f"\nChi tiết từng câu trả lời: {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
