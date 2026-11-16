// Bảng bên phải của một câu trả lời: Căn cứ (điều khoản trong ngữ cảnh), Đồ thị (đường đi GraphRAG), Quy trình (các bước).
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Boxes, ChevronRight, FileText, History, ListTree, TriangleAlert, Waypoints, Workflow, X } from "lucide-react";
import { navigate } from "../lib/router.js";
import { scrollIntoContainer } from "../lib/scroll.js";
import { EDGE_LABEL, ENTITY_TYPE, fmtDate, fmtMs, shortLabel, VERSION_LABEL } from "../lib/format.js";
import { SYSTEMS, sysOf } from "../lib/systems.js";
import ContextGraph, { EDGE_COLORS, NODE_COLORS } from "./ContextGraph.jsx";

function viaText(u) {
  const v = u.via;
  if (!v) return null;
  const from = shortLabel(v.from);
  if (v.kind === "THAM_CHIEU") return `Dẫn chiếu với ${from}`;
  if (v.kind === "HUONG_DAN") return `Hướng dẫn liên quan ${from}`;
  if (v.kind === "THUOC_CHA") return `Điều khoản chứa ${from}`;
  if (v.kind === "THUOC_CON") return `Nằm trong ${from}`;
  if (v.kind === "THUC_THE") return `Qua thực thể: ${(v.from || "").length > 42 ? v.from.slice(0, 42) + "…" : v.from}`;
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
        {u.origin === "seed" ? <span className="badge accent">Tìm trực tiếp</span>
          : u.origin === "entity" ? <span className="badge ok">{viaText(u)}</span> : <span className="badge graph">Từ đồ thị</span>}
        {u.cited && <span className="badge">Được trích dẫn</span>}
        {u.via && u.origin === "graph" && <span className="badge graph" title={`Cạnh ${u.via.type}`}>{viaText(u)}</span>}
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

function Communities({ list }) {
  if (!list?.length) return null;
  return (
    <>
      <div className="group-title"><Boxes size={13} /> Báo cáo cộng đồng ({list.length})</div>
      {list.map((c) => (
        <div key={c.id} className="src">
          <div className="src-title">{c.tieu_de}</div>
          <div className="src-meta"><span className="badge ok">Cộng đồng {c.id}</span><span className="badge">cấp {c.cap}</span>
            {c.muc_do != null && <span className="badge">mức độ {Number(c.muc_do).toFixed(1)}/10</span>}</div>
          <div className="src-text">{c.tom_tat}</div>
        </div>
      ))}
    </>
  );
}

function SourcesTab({ units, notes, citations, flashId, date, gctx, global }) {
  const cited = (citations || []).map((id) => units.find((u) => u.id === id)).filter(Boolean);
  const rest = units.filter((u) => !u.cited);
  const seeds = rest.filter((u) => u.origin === "seed");
  const graph = rest.filter((u) => u.origin === "graph");
  const ent = rest.filter((u) => u.origin === "entity");
  if (global) {
    return (
      <>
        <div className="banner warn small" style={{ marginBottom: 10 }}>Global search tổng hợp từ báo cáo cộng đồng của đồ thị thực thể: không trích dẫn điều khoản và không lọc theo ngày áp dụng.</div>
        <Communities list={gctx?.cong_dong} />
      </>
    );
  }
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
      {ent.length > 0 && <div className="group-title">Gắn với thực thể khớp câu hỏi ({ent.length})</div>}
      {ent.map((u) => <SourceCard key={u.id} u={u} flash={flashId === u.id} date={date} />)}
      {gctx && <Communities list={gctx.cong_dong} />}
      {units.length === 0 && !notes?.length && <div className="empty">Chưa có căn cứ</div>}
    </>
  );
}

function GraphTab({ graph, units, sys, gctx }) {
  const [sel, setSel] = useState(null);
  const ms = sys === "ms_graphrag";
  const elements = useMemo(() => ({
    nodes: (graph?.nodes || []).map((n) => {
      const ent = n.role === "entity" || n.role === "entity_nb";
      return {
        id: n.id, label: ent ? n.label : shortLabel(n.id), color: NODE_COLORS[n.role] || NODE_COLORS.path,
        size: n.role === "seed" ? 26 : n.role === "graph" || n.role === "entity" ? 20 : 14,
        level: n.role === "seed" ? 3 : n.role === "graph" ? 2 : 1, cited: n.cited || undefined,
        shape: ent ? "round-rectangle" : undefined,
      };
    }),
    edges: (graph?.edges || []).map((e) => ({ ...e, label: EDGE_LABEL[e.type] || e.type })),
  }), [graph]);
  const u = units.find((x) => x.id === sel);
  const e = ms && sel?.startsWith("E:") ? gctx?.thuc_the?.find((x) => "E:" + x.id === sel) : null;
  if (sys === "hybrid_rag") {
    return <div className="empty">Hybrid RAG (B1) không dùng đồ thị: ngữ cảnh chỉ gồm các điều khoản tìm trực tiếp bằng BM25 + vector và rerank.</div>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {ms ? (
        <div className="graph-legend">
          <span className="lg"><i style={{ background: NODE_COLORS.entity, borderRadius: 3 }} /> Thực thể khớp câu hỏi</span>
          <span className="lg"><i style={{ background: NODE_COLORS.entity_nb, borderRadius: 3 }} /> Thực thể lân cận</span>
          <span className="lg"><i style={{ background: NODE_COLORS.seed }} /> Điều khoản</span>
          <span className="lg"><em style={{ borderColor: EDGE_COLORS.LIEN_QUAN }} /> Quan hệ</span>
          <span className="lg"><em style={{ borderColor: EDGE_COLORS.XUAT_HIEN_TAI, borderTopStyle: "dotted" }} /> Xuất hiện tại</span>
        </div>
      ) : (
        <div className="graph-legend">
          <span className="lg"><i style={{ background: NODE_COLORS.seed }} /> Tìm trực tiếp</span>
          <span className="lg"><i style={{ background: NODE_COLORS.graph }} /> Thêm nhờ đồ thị</span>
          <span className="lg"><i style={{ background: "#fff", border: "3px solid #1c1c1a", width: 12, height: 12 }} /> Được trích dẫn</span>
          <span className="lg"><em style={{ borderColor: EDGE_COLORS.THAM_CHIEU }} /> Dẫn chiếu</span>
          <span className="lg"><em style={{ borderColor: EDGE_COLORS.THUOC, borderTopStyle: "dashed" }} /> Thuộc</span>
        </div>
      )}
      <div className="card" style={{ position: "relative", flex: 1, minHeight: 340 }}>
        <ContextGraph elements={elements} onTap={setSel} layout="cose" edgeLabels={false} maxZoom={1.1} />
      </div>
      <div style={{ marginTop: 10, minHeight: 90 }}>
        {u ? <SourceCard u={u} /> : e ? (
          <div className="src">
            <div className="src-title">{e.ten}</div>
            <div className="src-meta"><span className="badge ok">{ENTITY_TYPE[e.loai] || e.loai}</span>
              <span className="badge">{e.vai_tro === "khop" ? "Khớp câu hỏi" : "Lân cận"}</span></div>
            <div className="src-text">{e.mo_ta}</div>
          </div>
        ) : <div className="muted small">Bấm vào một node để xem nội dung. Rê chuột để làm nổi các liên kết.</div>}
      </div>
    </div>
  );
}

const STEP_COLORS = ["#a9b6f0", "#3451d1", "#6d83e3", "#e08a1e", "#a3a39b", "#1c1c1a"];

// Bảng trong chi tiết một bước: dòng có nội dung thì bấm để mở/đóng nội dung ngay bên dưới
function DetailTable({ b }) {
  const [open, setOpen] = useState(null);
  const [all, setAll] = useState(false);
  const LIMIT = 15;
  const rows = all ? b.dong : b.dong.slice(0, LIMIT);
  return (
    <div className="dt-block">
      <div className="dt-title">{b.tieu_de} <span className="muted">({b.dong.length})</span></div>
      <div className="dt-wrap">
        <table className="dt">
          <thead><tr>{b.cot.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {rows.map((d, i) => (
              <FragmentRow key={i} d={d} n={b.cot.length} open={open === i} onToggle={() => setOpen(open === i ? null : i)} />
            ))}
          </tbody>
        </table>
      </div>
      {b.dong.length > LIMIT && (
        <button className="link-btn" onClick={() => setAll(!all)}>{all ? "Thu gọn" : `Xem cả ${b.dong.length} dòng`}</button>
      )}
      {b.ghi_chu && <div className="dt-note">{b.ghi_chu}</div>}
    </div>
  );
}

function FragmentRow({ d, n, open, onToggle }) {
  const can = !!d.noi_dung;
  return (
    <>
      <tr className={`${d.kieu || ""} ${can ? "can-open" : ""} ${open ? "open" : ""}`} onClick={can ? onToggle : undefined}
        title={d.id || undefined}>
        {d.o.map((c, j) => <td key={j} className={typeof c === "number" || (typeof c === "string" && c.length < 28) ? "nw" : undefined}>{c == null || c === "" ? "–" : typeof c === "number" ? c.toLocaleString("vi-VN") : c}</td>)}
      </tr>
      {open && <tr className="dt-text"><td colSpan={n}>{d.id && <b>{d.id}</b>}{d.id && " · "}{d.noi_dung}</td></tr>}
    </>
  );
}

function StepDetail({ ct }) {
  return (
    <div className="step-more">
      {ct.thuat_toan?.length > 0 && (
        <>
          <div className="dt-title">Cách làm</div>
          <ol className="algo">{ct.thuat_toan.map((t, i) => <li key={i}>{t}</li>)}</ol>
        </>
      )}
      {ct.tham_so?.length > 0 && (
        <dl className="kv small-kv">{ct.tham_so.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></Fragment>)}</dl>
      )}
      {ct.bang?.map((b) => <DetailTable key={b.tieu_de} b={b} />)}
    </div>
  );
}

function StepsTab({ steps, result, units, sys, gctx }) {
  const [open, setOpen] = useState({});
  const coChiTiet = steps.some((s) => s.chi_tiet);
  const toggle = (k) => setOpen((o) => ({ ...o, [k]: !o[k] }));
  const total = steps.reduce((s, x) => s + (x.ms || 0), 0) || 1;
  const seeds = units.filter((u) => u.origin === "seed").length;
  const ctx = sys === "ms_graphrag"
    ? (result?.che_do === "global" ? `${gctx?.cong_dong?.length || 0} báo cáo cộng đồng`
      : `${units.length} điều khoản, ${gctx?.thuc_the?.length || 0} thực thể, ${gctx?.quan_he?.length || 0} quan hệ, ${gctx?.cong_dong?.length || 0} cộng đồng`)
    : sys === "hybrid_rag" ? `${units.length} điều khoản tìm trực tiếp`
      : `${units.length} điều khoản: ${seeds} tìm trực tiếp, ${units.length - seeds} thêm nhờ đồ thị`;
  return (
    <>
      <div className="kv" style={{ marginTop: 0 }}>
        <dt>Hệ thống</dt><dd>{SYSTEMS[sys]?.name}{result?.che_do === "global" ? " · global search" : ""}</dd>
        <dt>Tổng thời gian</dt><dd><b>{fmtMs(result?.latency_ms ?? total)}</b></dd>
        <dt>Ngày áp dụng</dt><dd>{fmtDate(result?.date)}</dd>
        <dt>Ngữ cảnh</dt><dd>{ctx}</dd>
        <dt>Trích dẫn</dt><dd>{result ? `${result.citations.length} hợp lệ${result.unknown_citations?.length ? `, ${result.unknown_citations.length} mã lạ` : ""}` : "…"}</dd>
        {result?.question_rewritten && (<><dt>Câu hỏi đầy đủ</dt><dd>{result.question_rewritten}</dd></>)}
      </div>
      <div className="timebar" title="Tỉ lệ thời gian của từng bước">
        {steps.map((s, i) => <span key={s.key} style={{ width: `${(100 * (s.ms || 0)) / total}%`, background: STEP_COLORS[i % 6] }} />)}
      </div>
      {coChiTiet && <div className="muted small" style={{ margin: "-4px 0 12px" }}>Bấm vào tên một bước để xem cách làm và các điều khoản được xét.</div>}
      <div className="steps">
        {steps.map((s, i) => (
          <div className="step" key={s.key}>
            <div className="step-num" style={{ borderColor: STEP_COLORS[i % 6] }}>{i + 1}</div>
            <div style={{ minWidth: 0 }}>
              {s.chi_tiet ? (
                <button className={`step-name step-toggle ${open[s.key] ? "on" : ""}`} onClick={() => toggle(s.key)} aria-expanded={!!open[s.key]}>
                  {s.label}<span className="step-more-btn"><ChevronRight size={14} /> Chi tiết</span>
                </button>
              ) : <div className="step-name">{s.label}</div>}
              <div className="step-detail">{s.detail}</div>
              {open[s.key] && s.chi_tiet && <StepDetail ct={s.chi_tiet} />}
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
  const date = msg?.result?.date || msg?.context?.date || msg?.date;
  const sys = sysOf(msg);
  const gctx = msg?.result?.graph_context || msg?.context?.graph_context;
  const global = (msg?.result?.che_do || msg?.che_do) === "global" && sys === "ms_graphrag";
  return (
    <aside className="panel">
      <div className="panel-head">
        <h3>Chi tiết câu trả lời{msg && <span className="sys-tag" style={{ "--c": SYSTEMS[sys]?.color }}>{SYSTEMS[sys]?.short}</span>}</h3>
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
        {msg && tab === "sources" && !(msg.result?.intent && msg.result.intent !== "luat") && <SourcesTab units={units} notes={notes} citations={msg.result?.citations} flashId={flashId} date={date} gctx={gctx} global={global} />}
        {msg && tab === "graph" && !(msg.result?.intent && msg.result.intent !== "luat") && <GraphTab graph={graph} units={units} sys={sys} gctx={gctx} />}
        {msg && tab === "steps" && <StepsTab steps={msg.steps || []} result={msg.result} units={units} sys={sys} gctx={gctx} />}
      </div>
    </aside>
  );
}
