"""Thử prompt sinh câu trả lời với NGỮ CẢNH CHUẨN (điều khoản gold), tách riêng khỏi phần truy xuất.

Phụ trách: TV1.   Cần OPENROUTER_API_KEY trong .env.
Chạy:  python scripts/thu_prompt.py                                   # 5 câu mẫu
       python scripts/thu_prompt.py data/eval/questions_TV1.jsonl --nhieu 8   # thêm 8 điều khoản gây nhiễu mỗi câu
       python scripts/thu_prompt.py --chi-in-prompt                   # chỉ in prompt, không gọi API

Mục đích:
  - Sửa prompt (graphrag/pipeline/prompts.py) trước khi có pipeline: lỗi ở đây là lỗi của bước SINH, không phải TRUY XUẤT.
  - Kết quả "ngữ cảnh chuẩn" là cận trên của Key-fact Accuracy, dùng trong phần phân tích lỗi của báo cáo NLP.
Ngữ cảnh = các gold có phiên bản hiệu lực tại ngày áp dụng (lấy từ versions.jsonl, giống fetch_valid),
cộng --nhieu điều khoản cùng Điều làm nhiễu. Kết quả gọi API được lưu đệm ở data/processed/cache/thu_prompt.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from graphrag.common.config import load_config  # noqa: E402
from graphrag.evaluation.metrics import citation_pr, key_fact_accuracy  # noqa: E402
from graphrag.parsing.versioning import valid_at  # noqa: E402
from graphrag.pipeline.prompts import SYSTEM, build_user, parse_citations  # noqa: E402


def dieu_cua(uid: str) -> str:
    parts = uid.split(".")
    return ".".join(parts[:2])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("questions", nargs="?", default=str(ROOT / "data/eval/questions_template.jsonl"))
    ap.add_argument("--nhieu", type=int, default=0, help="số điều khoản gây nhiễu (cùng Điều với gold) thêm vào ngữ cảnh")
    ap.add_argument("--chi-in-prompt", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    proc = ROOT / cfg["paths"]["processed"]
    rows = [json.loads(line) for line in open(proc / "versions.jsonl", encoding="utf-8")]
    qs = [json.loads(line) for line in open(args.questions, encoding="utf-8-sig") if line.strip()]
    cache_path = proc / "cache" / "thu_prompt.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    llm = None if args.chi_in_prompt else __import__("graphrag.llm", fromlist=["get_llm"]).get_llm(cfg)
    rng = random.Random(0)

    tong_kf, tong_p, tong_r, n_tien = 0.0, 0.0, 0.0, 0
    for q in qs:
        ngay = date.fromisoformat(q["ngay_ap_dung"])
        units = [u for g in q["gold_ids"] if (u := valid_at(rows, g, ngay))]
        if args.nhieu:
            dieus = {dieu_cua(g) for g in q["gold_ids"]}
            pool = [r for r in rows if r["cap"] in ("Khoan", "Diem") and dieu_cua(r["id"]) in dieus
                    and r["id"] not in q["gold_ids"] and valid_at([r], r["id"], ngay)]
            units += rng.sample(pool, min(args.nhieu, len(pool)))
            rng.shuffle(units)
        user = build_user(q["cau_hoi"], ngay, units)
        print("=" * 100)
        print(f"{q['id']} ({q['loai']}, {q['ngay_ap_dung']}): {q['cau_hoi']}")
        if args.chi_in_prompt:
            print(user)
            continue

        key = hashlib.sha1(f"{llm.model}\n{SYSTEM}\n{user}".encode()).hexdigest()
        if key not in cache:
            cache[key] = llm.generate(SYSTEM, user)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        ans = cache[key]
        ok, la = parse_citations(ans, [u["id"] for u in units])
        p, r = citation_pr(q["gold_ids"], ok)
        print(f"Ngữ cảnh: {len(units)} điều khoản · Đáp án chuẩn: {q['dap_an']}\n--- Trả lời ---\n{ans}\n---")
        line = f"Trích dẫn P={p:.2f} R={r:.2f}"
        if la:
            line += f" · mã lạ: {la}"
        if q["so_tien"]:
            kf = key_fact_accuracy(set(q["so_tien"]), ans)
            tong_kf += kf
            n_tien += 1
            line += f" · đúng số tiền: {'có' if kf else 'KHÔNG'}"
        print(line)
        tong_p += p
        tong_r += r

    if not args.chi_in_prompt and qs:
        print("=" * 100)
        print(f"{len(qs)} câu · Citation P={tong_p / len(qs):.2f} R={tong_r / len(qs):.2f}"
              + (f" · Key-fact Accuracy={tong_kf / n_tien:.2f} ({n_tien} câu có số tiền)" if n_tien else ""))


if __name__ == "__main__":
    main()
