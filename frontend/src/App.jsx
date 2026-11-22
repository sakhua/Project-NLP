// Khung giao diện: thanh bên (điều hướng, lịch sử trò chuyện, trạng thái máy chủ) + trang đang mở.
import { useEffect, useState } from "react";
import { BarChart3, BookOpen, History, LogOut, MessageSquare, Plus, Scale, Trash2, Waypoints } from "lucide-react";
import { api } from "./api.js";
import { clearSession, useSession } from "./lib/auth.js";
import { useConversations } from "./lib/conversations.js";
import { navigate, useRoute } from "./lib/router.js";
import AskPage from "./pages/AskPage.jsx";
import DocumentsPage from "./pages/DocumentsPage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";
import GraphPage from "./pages/GraphPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";

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

function UserChip({ user }) {
  if (!user) return null;
  return (
    <div className="user-chip">
      <span className="avatar">{(user.ho_ten || user.ten_dang_nhap || "?").trim().split(/\s+/).pop()[0].toUpperCase()}</span>
      <div className="grow">
        <div className="user-name">{user.ho_ten || user.ten_dang_nhap}</div>
        <div className="user-mail">{user.ten_dang_nhap}</div>
      </div>
      <button className="icon-btn" title="Đăng xuất" onClick={clearSession}><LogOut size={15} /></button>
    </div>
  );
}

/** Đọc cấu hình đăng nhập của backend; bắt buộc đăng nhập mà chưa có phiên thì hiện trang đăng nhập. */
export default function App() {
  const session = useSession();
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.authConfig().then(setCfg).catch((e) => setErr(e.message));
  }, []);
  if (err) {
    return (
      <div className="auth-page"><div className="login-card">
        <div className="banner error">{err}</div>
        <button className="btn" onClick={() => window.location.reload()}>Thử lại</button>
      </div></div>
    );
  }
  if (!cfg) {
    return <div className="auth-page"><div className="login-card muted">Đang kết nối máy chủ… (lần đầu có thể mất khoảng 1 phút)</div></div>;
  }
  if (cfg.bat_buoc && !session) return <LoginPage />;
  return <Shell user={cfg.bat_buoc ? session?.nguoi_dung : null} />;
}

function Shell({ user }) {
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
        <UserChip user={user} />
        <ServerStatus />
      </aside>
      <main className="main">
        {page === "chat" && <AskPage convId={route.param} convs={convs} query={route.query} />}
        {page === "docs" && <DocumentsPage docId={route.param} query={route.query} />}
        {page === "history" && <HistoryPage uid={route.param} />}
        {page === "graph" && <GraphPage uid={route.param} />}
        {page === "stats" && <AdminPage />}
      </main>
    </div>
  );
}
