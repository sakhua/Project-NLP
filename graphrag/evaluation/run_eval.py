"""Chạy đánh giá 4 hệ thống trên data/eval/questions.jsonl, xuất bảng theo loại câu hỏi.

Phụ trách: TV3 (môn NLP, môi trường local).
Chạy:  python -m graphrag.evaluation.run_eval --systems B1 B2 B3 GRAPH
"""
from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="+", default=["B1", "B2", "B3", "GRAPH"])
    ap.add_argument("--questions", default="data/eval/questions.jsonl")
    ap.add_argument("--out", default="data/processed/results.csv")
    ap.add_argument("--env", default="local", help="local (bge-m3, đầy đủ) hoặc cloud (để so sánh bản triển khai)")
    args = ap.parse_args()
    # TODO(TV3):
    # res = Resources(load_config(args.env))
    # chạy từng hệ thống (baseline_rag.answer / graph_rag.answer với res), tính metrics,
    # McNemar test, xuất CSV theo loại câu hỏi
    raise NotImplementedError(args)


if __name__ == "__main__":
    main()
