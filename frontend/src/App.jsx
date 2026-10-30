// Khung giao diện: thanh bên (điều hướng, lịch sử trò chuyện, trạng thái máy chủ) + trang đang mở.
import { useEffect, useState } from "react";
import { BarChart3, BookOpen, History, MessageSquare, Plus, Scale, Trash2, Waypoints } from "lucide-react";
import { api } from "./api.js";
import { useConversations } from "./lib/conversations.js";
import { navigate, useRoute } from "./lib/router.js";
import AskPage from "./pages/AskPage.jsx";
import DocumentsPage from "./pages/DocumentsPage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";
import GraphPage from "./pages/GraphPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";

const NAV = [
  { key: "chat", label: "Trò chuyện", icon: MessageSquare },
  { key: "docs", label: "Tra cứu văn bản", icon: BookOpen },
  { key: "history", label: "Lịch sử sửa đổi", icon: History },
  { key: "graph", label: "Khám phá đồ thị", icon: Waypoints },
  { key: "stats", label: "Thống kê", icon: BarChart3 },
];

function ServerStatus() {
  const [s, setS] = useState(null);
  useEffect(() => {
    let alive = true;
    const check = () => api.healthDb().then((d) => alive && setS(d)).catch(() => alive && setS({ down: true }));
    check();
    const t = setInterval(check, 30000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const row = (label, part, extra) => (
    <div className="status-row">
      <span className={`dot ${s == null ? "" : part?.ok ? "ok" : "bad"}`} />
      <span className="grow">{label}</span>
      <span>{s == null ? "…" : part?.ok ? extra : "lỗi"}</span>
    </div>
  );
  return (
    <div className="side-foot">
      {s?.down ? (
        <div className="status-row"><span className="dot bad" /> Không kết nối được backend</div>
      ) : (
        <>
          {row("PostgreSQL", s?.postgres, s?.postgres?.ok && `${s.postgres.don_vi.toLocaleString("vi-VN")} phiên bản`)}
          {row("Neo4j", s?.neo4j, s?.neo4j?.ok && `${s.neo4j.nodes.toLocaleString("vi-VN")} node`)}
        </>
      )}
    </div>
  );
}

export default function App() {
  const route = useRoute();
  const convs = useConversations();
  const page = NAV.some((n) => n.key === route.page) ? route.page : "chat";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Scale size={18} /></div>
          <div>
            <div className="brand-name">Luật Giao thông AI</div>
            <div className="brand-sub">Hỏi đáp pháp luật · GraphRAG</div>
          </div>
        </div>
        <div style={{ padding: "4px 12px 8px" }}>
          <button className="btn" style={{ width: "100%", justifyContent: "flex-start" }} onClick={() => navigate("chat")}>
            <Plus size={16} /> Cuộc trò chuyện mới
          </button>
        </div>
        <nav className="nav">
          {NAV.map(({ key, label, icon: Icon }) => (
            <button key={key} className={`nav-item ${page === key ? "active" : ""}`} onClick={() => navigate(key)}>
              <Icon size={17} /> {label}
            </button>
          ))}
        </nav>
        <div className="side-section">
          <span>Gần đây</span>
          {convs.list.length > 0 && (
            <button className="icon-btn" title="Xóa toàn bộ lịch sử" onClick={() => {
              if (window.confirm("Xóa toàn bộ lịch sử trò chuyện trên trình duyệt này?")) { convs.clear(); navigate("chat"); }
            }}><Trash2 size={14} /></button>
          )}
        </div>
        <div className="convs">
          {convs.list.length === 0 && <div className="muted small" style={{ padding: "4px 10px" }}>Chưa có cuộc trò chuyện nào</div>}
          {convs.list.map((c) => (
            <div key={c.id} className={`conv ${page === "chat" && route.param === c.id ? "active" : ""}`}
              onClick={() => navigate("chat", c.id)}>
              <span className="conv-title">{c.title}</span>
              <button className="icon-btn" title="Xóa" onClick={(e) => {
                e.stopPropagation(); convs.remove(c.id); if (route.param === c.id) navigate("chat");
              }}><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        <ServerStatus />
      </aside>
      <main className="main">
        {page === "chat" && <AskPage key={route.param || "new"} convId={route.param} convs={convs} query={route.query} />}
        {page === "docs" && <DocumentsPage docId={route.param} query={route.query} />}
        {page === "history" && <HistoryPage uid={route.param} />}
        {page === "graph" && <GraphPage uid={route.param} />}
        {page === "stats" && <AdminPage />}
      </main>
    </div>
  );
}
