// Khung giao diện: thanh điều hướng 4 trang + trạng thái máy chủ. Phụ trách: TV3.
import { useEffect, useState } from "react";
import { api } from "./api.js";
import AskPage from "./pages/AskPage.jsx";
import DocumentsPage from "./pages/DocumentsPage.jsx";
import GraphPage from "./pages/GraphPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";

const PAGES = [
  { key: "ask", label: "Hỏi đáp" },
  { key: "docs", label: "Tra cứu văn bản" },
  { key: "graph", label: "Đồ thị liên kết" },
  { key: "admin", label: "Quản trị" },
];

export default function App() {
  const [page, setPage] = useState("ask");
  const [graphId, setGraphId] = useState("");
  const [server, setServer] = useState("checking"); // checking | ok | down

  useEffect(() => {
    api.health().then(() => setServer("ok")).catch(() => setServer("down"));
  }, []);

  const openGraph = (uid) => { setGraphId(uid); setPage("graph"); };

  return (
    <div className="wrap">
      <header>
        <h1>Hỏi đáp pháp luật giao thông đường bộ</h1>
        <p className="muted">Trả lời có trích dẫn điều khoản, lọc theo ngày áp dụng (GraphRAG)</p>
        <nav>
          {PAGES.map((p) => (
            <button key={p.key} className={page === p.key ? "tab active" : "tab"} onClick={() => setPage(p.key)}>
              {p.label}
            </button>
          ))}
        </nav>
        {server === "checking" && <div className="banner">Đang kết nối máy chủ… lần đầu có thể mất khoảng 1 phút.</div>}
        {server === "down" && <div className="banner error">Không kết nối được máy chủ. Tải lại trang sau ít phút.</div>}
      </header>
      <main>
        {page === "ask" && <AskPage onOpenGraph={openGraph} />}
        {page === "docs" && <DocumentsPage onOpenGraph={openGraph} />}
        {page === "graph" && <GraphPage initialId={graphId} />}
        {page === "admin" && <AdminPage />}
      </main>
      <footer className="muted">Thông tin chỉ mang tính tham khảo; đối chiếu văn bản gốc trước khi áp dụng.</footer>
    </div>
  );
}
