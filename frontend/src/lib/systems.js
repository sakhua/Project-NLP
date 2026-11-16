// Ba hệ thống hỏi đáp (khớp graphrag/pipeline/he_thong.py): tên, màu, thứ tự các bước để hiện tiến trình.
export const SYS_ORDER = ["hybrid_graphrag", "hybrid_rag", "ms_graphrag"];

export const SYSTEMS = {
  hybrid_graphrag: {
    short: "Hybrid GraphRAG", name: "Hybrid GraphRAG (đề xuất)", tag: "Đề xuất", color: "#3451d1",
    desc: "Tìm kiếm lai BM25 + vector, rerank, mở rộng trên đồ thị văn bản (dẫn chiếu, hướng dẫn)",
    steps: ["rewrite", "intent", "search", "rerank", "graph", "context", "generate"],
  },
  hybrid_rag: {
    short: "Hybrid RAG", name: "Hybrid RAG (B1)", tag: "B1", color: "#55554f",
    desc: "Tìm kiếm lai BM25 + vector, gộp RRF, rerank; không dùng đồ thị",
    steps: ["rewrite", "intent", "search", "rerank", "context", "generate"],
  },
  ms_graphrag: {
    short: "GraphRAG (MS)", name: "GraphRAG kiểu Microsoft (B2)", tag: "B2", color: "#1f8a4c",
    desc: "Đồ thị thực thể do LLM trích, cộng đồng Leiden; local search (hoặc global cho câu hỏi tổng quan)",
    steps: ["rewrite", "intent", "entities", "expand", "community", "units", "context", "generate"],
    stepsGlobal: ["rewrite", "intent", "communities", "map", "reduce"],
  },
};

export const STEP_PENDING = {
  rewrite: "Đang hiểu câu hỏi theo ngữ cảnh…",
  intent: "Đang phân loại câu hỏi…",
  search: "Đang tìm kiếm BM25 + vector…",
  rerank: "Đang lọc theo ngày áp dụng và xếp hạng…",
  graph: "Đang mở rộng trên đồ thị tri thức…",
  context: "Đang ghép ngữ cảnh…",
  generate: "Đang soạn câu trả lời…",
  entities: "Đang tìm thực thể liên quan…",
  expand: "Đang mở rộng sang thực thể lân cận…",
  community: "Đang lấy báo cáo cộng đồng…",
  units: "Đang lấy điều khoản gắn với thực thể…",
  communities: "Đang chọn báo cáo cộng đồng…",
  map: "Đang rút ý từ các báo cáo (map)…",
  reduce: "Đang tổng hợp câu trả lời (reduce)…",
};

export const stepOrder = (sys, cheDo) =>
  (sys === "ms_graphrag" && cheDo === "global" ? SYSTEMS.ms_graphrag.stepsGlobal : (SYSTEMS[sys] || SYSTEMS.hybrid_graphrag).steps);

export const sysOf = (msg) => msg?.result?.he_thong || msg?.he_thong || "hybrid_graphrag";
