"""Chạy đánh giá các hệ thống trên bộ câu hỏi, chấm bằng 6 độ đo không dùng LLM, kiểm định paired bootstrap (môn NLP).

  python -m graphrag.evaluation.run_eval --systems GRAPH B1 B2 --questions data/eval/questions.jsonl

  GRAPH = Hybrid GraphRAG (đề xuất) · B1 = Hybrid RAG · B2 = GraphRAG kiểu Microsoft
Thực chất gọi scripts/chay_bo_test.py (cùng cách chấm, cùng báo cáo trong data/eval/ket_qua/).
"""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

MA = {"GRAPH": "hybrid_graphrag", "B1": "hybrid_rag", "B2": "ms_graphrag"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="+", default=list(MA), choices=list(MA))
    ap.add_argument("--questions", default="data/eval/bo_test_tu_dong.jsonl")
    args, rest = ap.parse_known_args()
    root = Path(__file__).resolve().parents[2]
    sys.argv = ["chay_bo_test.py", "--file", args.questions, "--he-thong", *[MA[s] for s in args.systems], *rest]
    runpy.run_path(str(root / "scripts/chay_bo_test.py"), run_name="__main__")


if __name__ == "__main__":
    main()
