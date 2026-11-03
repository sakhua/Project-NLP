"""Chấm câu trả lời bằng thư viện RAGAS (Faithfulness, Answer Relevance, Context Precision, Context Recall).

Cài: pip install -e ".[ragas]"
Dùng: scripts/chay_bo_test.py --ragas  (hoặc --cham-lai <file> --ragas để chấm lại kết quả cũ)

- Bốn độ đo dùng LLM làm giám khảo, gọi qua OpenRouter (mặc định evaluation.judge_model = openai/gpt-4o,
  mạnh hơn mô hình sinh câu trả lời để không "tự chấm cho mình").
- Answer Relevance cần thêm embedding: dùng lại embedder của dự án (bge-m3, đa ngôn ngữ).
- Thêm hai độ đo KHÔNG dùng LLM, tính theo mã điều khoản gold (chính xác, không tốn tiền):
  Context Precision (ID) = tỉ lệ đơn vị trong ngữ cảnh là gold; Context Recall (ID) = tỉ lệ gold có trong ngữ cảnh.

Lưu ý khi đọc: Faithfulness chỉ đo câu trả lời có bám ngữ cảnh không, KHÔNG so với đáp án chuẩn. Nếu hệ thống
lấy nhầm phiên bản luật cũ rồi trả lời đúng theo phiên bản đó thì Faithfulness vẫn cao — vì vậy vẫn phải xem
Key-fact / Temporal Accuracy (cột "Đúng") của chay_bo_test.py.
"""
from __future__ import annotations

import asyncio
import math
import warnings

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# tên cột trong kết quả RAGAS → tên hiển thị trong báo cáo
COT = {
    "faithfulness": "Faithfulness",
    "answer_relevancy": "Answer Relevance",
    "llm_context_precision_with_reference": "Context Precision",
    "context_recall": "Context Recall",
    "id_based_context_precision": "Context Precision (ID)",
    "id_based_context_recall": "Context Recall (ID)",
}


def _embeddings(cfg: dict):
    from ragas.embeddings import BaseRagasEmbeddings

    from graphrag.embedding import get_embedder

    emb = get_embedder(cfg)

    class DuAnEmbeddings(BaseRagasEmbeddings):
        """Bọc embedder của dự án (bge-m3 qua OpenRouter hoặc chạy trên máy) cho RAGAS."""

        def embed_query(self, text: str) -> list[float]:
            return emb.encode_queries([text])[0].tolist()

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return emb.encode_documents(texts).tolist()

        async def aembed_query(self, text: str) -> list[float]:
            return await asyncio.to_thread(self.embed_query, text)

        async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
            return await asyncio.to_thread(self.embed_documents, texts)

    return DuAnEmbeddings()


def _llm(cfg: dict, model: str):
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper

    key = cfg["secrets"]["openrouter_api_key"]
    if not key:
        raise RuntimeError("Thiếu OPENROUTER_API_KEY (đặt trong .env)")
    chat = ChatOpenAI(model=model, base_url=OPENROUTER_BASE, api_key=key, temperature=0, timeout=120,
                      max_retries=3, default_headers={"X-Title": "GraphRAG luat GTDB - RAGAS"})
    return LangchainLLMWrapper(chat, bypass_n=True)   # OpenRouter không chắc hỗ trợ tham số n → gọi lần lượt


def _so(x) -> float | None:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else round(x, 4)


def cham_ragas(rows: list[dict], cfg: dict, model: str | None = None, song_song: int = 4,
               co_llm: bool = True) -> list[dict]:
    """rows: kết quả của chay_bo_test.py (cần cau_hoi, tra_loi, ngu_canh, ngu_canh_text, dap_an, gold_ids).

    Trả về danh sách điểm (cùng thứ tự rows), mỗi phần tử {tên cột RAGAS: điểm 0–1 hoặc None}.
    co_llm=False: chỉ tính hai độ đo theo mã (không gọi API).
    """
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from ragas import EvaluationDataset, RunConfig, SingleTurnSample, evaluate
    from ragas.metrics import (Faithfulness, IDBasedContextPrecision, IDBasedContextRecall,
                               LLMContextPrecisionWithReference, LLMContextRecall, ResponseRelevancy)

    samples = []
    for r in rows:
        samples.append(SingleTurnSample(
            user_input=f"{r['cau_hoi']} (ngày áp dụng: {r['ngay_ap_dung']})",
            response=r.get("tra_loi") or "",
            retrieved_contexts=r.get("ngu_canh_text") or [""],
            reference=f"{r['dap_an']} Căn cứ: {r.get('can_cu', '')}",
            retrieved_context_ids=r.get("ngu_canh") or [],
            reference_context_ids=r.get("gold_ids") or [],
        ))
    metrics = [IDBasedContextPrecision(), IDBasedContextRecall()]
    kwargs = {}
    if co_llm:
        metrics = [Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithReference(), LLMContextRecall()] + metrics
        kwargs = {"llm": _llm(cfg, model or cfg.get("evaluation", {}).get("judge_model", "openai/gpt-4o")),
                  "embeddings": _embeddings(cfg)}
    result = evaluate(EvaluationDataset(samples=samples), metrics=metrics,
                      run_config=RunConfig(max_workers=song_song, timeout=300, max_retries=5),
                      raise_exceptions=False, show_progress=True, **kwargs)
    df = result.to_pandas()
    cols = [m.name for m in metrics]
    return [{c: _so(df.iloc[i][c]) if c in df.columns else None for c in cols} for i in range(len(rows))]
