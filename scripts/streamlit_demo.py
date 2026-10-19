"""Giao diện thử nhanh cho môn NLP (chạy trên máy, không triển khai lên cloud).

Bản web chính thức nằm ở frontend/ (React) + backend/ (FastAPI).
Chạy:  streamlit run scripts/streamlit_demo.py
"""
import sys
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

st.set_page_config(page_title="Hỏi đáp luật giao thông", layout="wide")
st.title("Hỏi đáp pháp luật giao thông đường bộ (GraphRAG)")

question = st.text_area("Câu hỏi", placeholder="Ví dụ: Ô tô cá nhân nhận chở người thu tiền bị phạt bao nhiêu?")
ngay = st.date_input("Ngày áp dụng", value=date.today())
system = st.selectbox("Hệ thống", ["GraphRAG", "B3 – RAG hybrid", "B2 – RAG vector", "B1 – BM25"])

if st.button("Trả lời") and question.strip():
    st.info("Pipeline chưa được kết nối. TODO(TV1): tạo Resources(load_config('local')) "
            "rồi gọi graphrag.pipeline.graph_rag.answer(res, question, ngay).")
