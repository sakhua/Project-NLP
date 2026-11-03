// Bảng bên phải của một câu trả lời: Căn cứ (điều khoản trong ngữ cảnh), Đồ thị (đường đi GraphRAG), Quy trình (các bước).
import { useEffect, useMemo, useRef, useState } from "react";
import { FileText, History, ListTree, TriangleAlert, Waypoints, Workflow, X } from "lucide-react";
import { navigate } from "../lib/router.js";
import { scrollIntoContainer } from "../lib/scroll.js";
import { EDGE_LABEL, fmtDate, fmtMs, shortLabel, VERSION_LABEL } from "../lib/format.js";
import ContextGraph, { EDGE_COLORS, NODE_COLORS } from "./ContextGraph.jsx";

function viaText(u) {
  const v = u.via;
  if (!v) return null;
  const from = shortLabel(v.from);
  if (v.kind === "THAM_CHIEU") return `Dẫn chiếu với ${from}`;
  if (v.kind === "HUONG_DAN") return `Hướng dẫn liên quan ${from}`;
  if (v.kind === "THUOC_CHA") return `Điều khoản chứa ${from}`;
  if (v.kind === "THUOC_CON") return `Nằm trong ${from}`;
  return `${EDGE_LABEL[v.type] || v.type} · ${from}`;
}

export function SourceCard({ u, flash, date }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => { if (flash) scrollIntoContainer(ref.current, ref.current?.closest(".panel-body")); }, [flash]);
  const ctx = (u.ngu_canh || "").split(" – ").slice(-1)[0];
  return (
    <div ref={ref} className={`src ${u.cited ? "cited" : ""} ${flash ? "flash" : ""}`} id={`src-${u.id}`}>
      <div className="src-title">{u.ten}</div>
      <div className="src-meta">
        {u.origin === "seed" ? <span className="badge accent">Tìm trực tiếp</span> : <span className="badge graph">Từ đồ thị</span>}
        {u.cited && <span className="badge">Được trích dẫn</span>}
        {u.via && <span className="badge graph" title={`Cạnh ${u.via.type}`}>{viaText(u)}</span>}
        <span className="badge">Hiệu lực từ {fmtDate(u.hieu_luc_tu)}{u.hieu_luc_den ? ` đến ${fmtDate(u.hieu_luc_den)}` : ""}</span>
        {u.nguon_sua_doi && <span className="badge warn">{VERSION_LABEL[u.loai_phien_ban] || "Sửa đổi"} bởi {u.nguon_ten}</span>}
      </div>
      {ctx && u.cap === "Diem" && <div className="src-ctx">{ctx.length > 160 ? ctx.slice(0, 160) + "…" : ctx}</div>}
      <div className={`src-text ${open ? "" : "clamp"}`} onClick={() => setOpen(!open)}>{u.noi_dung}</div>
      <div className="src-actions">
        <button className="link-btn" onClick={() => navigate("docs", u.van_ban_id, { unit: u.id, date })}><FileText size={13} /> Văn bản</button>
        <button className="link-btn" onClick={() => navigate("history", u.id)}><History size={13} /> Lịch sử</button>
        <button className="link-btn" onClick={() => navigate("graph", u.id)}><Waypoints size={13} /> Đồ thị</button>
      </div>
    </div>
  );
}

function SourcesTab({ units, notes, citations, flashId, date }) {
  const cited = (citations || []).map((id) => units.find((u) => u.id === id)).filter(Boolean);
  const rest = units.filter((u) => !u.cited);
  const seeds = rest.filter((u) => u.origin === "seed");
  const graph = rest.filter((u) => u.origin === "graph");
  return (
    <>
      {notes?.length > 0 && (
        <>
          <div className="group-title"><TriangleAlert size={13} /> Không áp dụng tại ngày đã chọn</div>
          {notes.map((n) => (
            <div key={n.id} className="note-card">
              <b>{n.ten}</b>: {n.trang_thai === "chua_hieu_luc" ? `chưa có hiệu lực (từ ${fmtDate(n.ngay)})` : `đã hết hiệu lực (từ ${fmtDate(n.ngay)})`}.
              <div style={{ marginTop: 4, opacity: .85 }}>{n.noi_dung.slice(0, 220)}{n.noi_dung.length > 220 ? "…" : ""}</div>
            </div>
          ))}
        </>
      )}
      {cited.length > 0 && <div className="group-title">Được trích dẫn ({cited.length})</div>}
      {cited.map((u) => <SourceCard key={u.id} u={u} flash={flashId === u.id} date={date} />)}
      {seeds.length > 0 && <div className="group-title">Tìm trực tiếp ({seeds.length})</div>}
      {seeds.map((u) => <SourceCard key={u.id} u={u} flash={flashId === u.id} date={date} />)}
      {graph.length > 0 && <div className="group-title">Mở rộng từ đồ thị ({graph.length})</div>}
      {graph.map((u) => <SourceCard key={u.id} u={u} flash={flashId === u.id} date={date} />)}
      {units.length === 0 && !notes?.length && <div className="empty">Chưa có căn cứ</div>}
    </>
  );
}

function GraphTab({ graph, units }) {
  const [sel, setSel] = useState(null);
  const elements = useMemo(() => ({
    nodes: (graph?.nodes || []).map((n) => ({
      id: n.id, label: shortLabel(n.id), color: NODE_COLORS[n.role] || NODE_COLORS.path,
      size: n.role === "seed" ? 26 : n.role === "graph" ? 20 : 14, level: n.role === "seed" ? 3 : n.role === "graph" ? 2 : 1,
      cited: n.cited || undefined,
    })),
    edges: (graph?.edges || []).map((e) => ({ ...e, label: EDGE_LABEL[e.type] || e.type })),
  }), [graph]);
  const u = units.find((x) => x.id === sel);
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="graph-legend">
        <span className="lg"><i style={{ background: NODE_COLORS.seed }} /> Tìm trực tiếp</span>
        <span className="lg"><i style={{ background: NODE_COLORS.graph }} /> Thêm nhờ đồ thị</span>
        <span className="lg"><i style={{ background: "#fff", border: "3px solid #1c1c1a", width: 12, height: 12 }} /> Được trích dẫn</span>
        <span className="lg"><em style={{ borderColor: EDGE_COLORS.THAM_CHIEU }} /> Dẫn chiếu</span>
        <span className="lg"><em style={{ borderColor: EDGE_COLORS.THUOC, borderTopStyle: "dashed" }} /> Thuộc</span>
      </div>
      <div className="card" style={{ position: "relative", flex: 1, minHeight: 340 }}>
        <ContextGraph elements={elements} onTap={setSel} layout="cose" edgeLabels={false} maxZoom={1.1} />
      </div>
      <div style={{ marginTop: 10, minHeight: 90 }}>
        {u ? <SourceCard u={u} /> : <div className="muted small">Bấm vào một node để xem nội dung. Rê chuột để làm nổi các liên kết.</div>}
      </div>
    </div>
  );
}

const STEP_COLORS = ["#a9b6f0", "#3451d1", "#6d83e3", "#e08a1e", "#a3a39b", "#1c1c1a"];

function StepsTab({ steps, result, units }) {
  const total = steps.reduce((s, x) => s + (x.ms || 0), 0) || 1;
  const seeds = units.filter((u) => u.origin === "seed").length;
  return (
    <>
      <div className="kv" style={{ marginTop: 0 }}>
        <dt>Tổng thời gian</dt><dd><b>{fmtMs(result?.latency_ms ?? total)}</b></dd>
        <dt>Ngày áp dụng</dt><dd>{fmtDate(result?.date)}</dd>
        <dt>Ngữ cảnh</dt><dd>{units.length} điều khoản: {seeds} tìm trực tiếp, {units.length - seeds} thêm nhờ đồ thị</dd>
        <dt>Trích dẫn</dt><dd>{result ? `${result.citations.length} hợp lệ${result.unknown_citations?.length ? `, ${result.unknown_citations.length} mã lạ` : ""}` : "…"}</dd>
        {result?.question_rewritten && (<><dt>Câu hỏi đầy đủ</dt><dd>{result.question_rewritten}</dd></>)}
      </div>
      <div className="timebar" title="Tỉ lệ thời gian của từng bước">
        {steps.map((s, i) => <span key={s.key} style={{ width: `${(100 * (s.ms || 0)) / total}%`, background: STEP_COLORS[i % 6] }} />)}
      </div>
      <div className="steps">
        {steps.map((s, i) => (
          <div className="step" key={s.key}>
            <div className="step-num" style={{ borderColor: STEP_COLORS[i % 6] }}>{i + 1}</div>
            <div>
              <div className="step-name">{s.label}</div>
              <div className="step-detail">{s.detail}</div>
            </div>
            <div className="step-ms">{fmtMs(s.ms)}</div>
          </div>
        ))}
      </div>
    </>
  );
}

export default function AnswerPanel({ msg, tab, setTab, flashId, onClose }) {
  const units = msg?.result?.units || msg?.context?.units || [];
  const graph = msg?.result?.graph || msg?.context?.graph;
  const notes = msg?.result?.notes || msg?.context?.notes || [];
  const date = msg?.result?.date || msg?.context?.date;
  return (
    <aside className="panel">
      <div className="panel-head">
        <h3>Chi tiết câu trả lời</h3>
        <button className="icon-btn" onClick={onClose} title="Đóng"><X size={16} /></button>
      </div>
      <div className="tabs">
        <button className={`tab ${tab === "sources" ? "active" : ""}`} onClick={() => setTab("sources")}><ListTree size={14} /> Căn cứ ({units.length})</button>
        <button className={`tab ${tab === "graph" ? "active" : ""}`} onClick={() => setTab("graph")}><Waypoints size={14} /> Đồ thị</button>
        <button className={`tab ${tab === "steps" ? "active" : ""}`} onClick={() => setTab("steps")}><Workflow size={14} /> Quy trình</button>
      </div>
      <div className="panel-body" style={tab === "graph" ? { display: "flex", flexDirection: "column" } : undefined}>
        {!msg && <div className="empty">Chọn một câu trả lời để xem căn cứ</div>}
        {msg?.result?.intent && msg.result.intent !== "luat" && tab !== "steps" && (
          <div className="empty">Câu này không phải câu hỏi pháp luật giao thông nên hệ thống không tra cứu văn bản.</div>
        )}
        {msg && tab === "sources" && !(msg.result?.intent && msg.result.intent !== "luat") && <SourcesTab units={units} notes={notes} citations={msg.result?.citations} flashId={flashId} date={date} />}
        {msg && tab === "graph" && !(msg.result?.intent && msg.result.intent !== "luat") && <GraphTab graph={graph} units={units} />}
        {msg && tab === "steps" && <StepsTab steps={msg.steps || []} result={msg.result} units={units} />}
      </div>
    </aside>
  );
}
