// F3 Khám phá đồ thị tri thức: tìm một điều khoản, bấm đúp để mở rộng các node lân cận. Phụ trách: TV2.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { History, Maximize2, MessageSquare, RotateCcw, Search, Trash2, Waypoints } from "lucide-react";
import { api } from "../api.js";
import ContextGraph, { EDGE_COLORS, NODE_COLORS } from "../components/ContextGraph.jsx";
import { CAP_LABEL, EDGE_LABEL, fmtDate, longLabel, shortLabel, VERSION_LABEL } from "../lib/format.js";
import { navigate } from "../lib/router.js";

const START = "ND168_2024.D6.K9.b";
const EDGE_TYPES = ["THAM_CHIEU", "THUOC", "SUA_DOI", "BO_SUNG", "THAY_THE", "BAI_BO", "HUONG_DAN"];

function SearchBox({ onPick }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState([]);
  const [open, setOpen] = useState(false);
  const [hl, setHl] = useState(0);
  useEffect(() => {
    if (q.trim().length < 2) { setRes([]); return; }
    const t = setTimeout(() => api.search(q.trim(), 12).then((r) => { setRes(r); setHl(0); }).catch(() => setRes([])), 250);
    return () => clearTimeout(t);
  }, [q]);
  const pick = (r) => { onPick(r.id); setOpen(false); setQ(""); };
  return (
    <div className="float-card" style={{ position: "relative", width: 420, padding: 6 }}>
      <div className="search-box">
        <Search size={15} />
        <input className="input" style={{ border: 0, boxShadow: "none" }} value={q} placeholder="Tìm điều khoản theo mã hoặc nội dung…"
          onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") setHl((h) => Math.min(h + 1, res.length - 1));
            if (e.key === "ArrowUp") setHl((h) => Math.max(h - 1, 0));
            if (e.key === "Enter" && res[hl]) pick(res[hl]);
          }} />
      </div>
      {open && res.length > 0 && (
        <div className="float-card results">
          {res.map((r, i) => (
            <button key={r.id} className={`result ${i === hl ? "hl" : ""}`} onMouseDown={() => pick(r)}>
              <div className="t">{r.ten}</div>
              <div className="d">{r.noi_dung}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function GraphPage({ uid }) {
  const [nodes, setNodes] = useState({});   // id -> {id, label(cap), expanded}
  const [edges, setEdges] = useState({});   // key -> {source, target, type}
  const [sel, setSel] = useState(null);
  const [detail, setDetail] = useState(null);
  const [hidden, setHidden] = useState(new Set());
  const [err, setErr] = useState("");
  const cyRef = useRef(null);
  const focusId = uid || START;

  const expand = useCallback(async (id, reset = false) => {
    setErr("");
    try {
      const g = await api.graph(id, 40);
      setNodes((prev) => {
        const next = reset ? {} : { ...prev };
        next[g.center.id] = { ...(next[g.center.id] || {}), id: g.center.id, cap: g.center.label, expanded: true };
        g.neighbors.forEach((n) => { if (!next[n.id]) next[n.id] = { id: n.id, cap: n.label, expanded: false }; });
        return next;
      });
      setEdges((prev) => {
        const next = reset ? {} : { ...prev };
        g.neighbors.forEach((n) => {
          const [s, t] = n.outgoing ? [g.center.id, n.id] : [n.id, g.center.id];
          next[`${s}|${n.rel}|${t}`] = { source: s, target: t, type: n.rel };
        });
        return next;
      });
    } catch (e) { setErr(e.message); }
  }, []);

  useEffect(() => { expand(focusId, true); setSel(focusId); }, [focusId, expand]);
  useEffect(() => {
    if (!sel) return;
    setDetail(null);
    if (!/\./.test(sel)) { setDetail({ id: sel, ten: longLabel(sel), versions: [], sua_doi_boi: [] }); return; }
    api.unit(sel).then(setDetail).catch(() => setDetail({ id: sel, ten: longLabel(sel), versions: [], sua_doi_boi: [] }));
  }, [sel]);

  const elements = useMemo(() => {
    const es = Object.values(edges).filter((e) => !hidden.has(e.type));
    const keep = new Set([focusId]);
    es.forEach((e) => { keep.add(e.source); keep.add(e.target); });
    return {
      nodes: Object.values(nodes).filter((n) => keep.has(n.id)).map((n) => ({
        id: n.id, label: shortLabel(n.id), color: NODE_COLORS[n.cap] || "#a3a39b",
        size: n.id === focusId ? 30 : n.expanded ? 24 : n.cap === "VanBan" ? 26 : 18, focus: n.id === focusId || undefined,
        level: n.id === focusId ? 3 : n.expanded ? 2 : 1,
      })),
      edges: es.map((e) => ({ ...e, label: EDGE_LABEL[e.type] || e.type })),
    };
  }, [nodes, edges, hidden, focusId]);

  const typesPresent = EDGE_TYPES.filter((t) => Object.values(edges).some((e) => e.type === t));
  const cur = detail?.versions?.length ? detail.versions[detail.versions.length - 1] : null;
  const neighbors = Object.values(edges).filter((e) => e.source === sel || e.target === sel);

  return (
    <div className="explorer">
      <div className="canvas-wrap">
        <ContextGraph elements={elements} layout="concentric" cyRef={cyRef} maxZoom={1.15} onTap={setSel} onDblTap={(id) => { setSel(id); expand(id); }} />
        <div className="float-bar">
          <SearchBox onPick={(id) => navigate("graph", id)} />
          <span className="grow" />
          <div className="float-card" style={{ padding: "8px 12px", fontSize: 12.5, color: "var(--text-2)" }}>
            {Object.keys(nodes).length} node · {Object.keys(edges).length} cạnh · <b>bấm đúp</b> để mở rộng
          </div>
        </div>
        {err && <div className="banner error" style={{ position: "absolute", top: 70, left: 14, zIndex: 10 }}>{err}</div>}
        <div className="float-card float-legend">
          <div className="graph-legend" style={{ marginBottom: 6 }}>
            {["VanBan", "Chuong", "Dieu", "Khoan", "Diem"].map((c) => (
              <span key={c} className="lg"><i style={{ background: NODE_COLORS[c] }} /> {CAP_LABEL[c]}</span>
            ))}
          </div>
          <div className="graph-legend" style={{ marginBottom: 0 }}>
            {typesPresent.map((t) => (
              <label key={t} className="lg" style={{ cursor: "pointer", opacity: hidden.has(t) ? 0.4 : 1 }}>
                <input type="checkbox" checked={!hidden.has(t)} style={{ margin: 0 }} onChange={() => setHidden((h) => {
                  const n = new Set(h); n.has(t) ? n.delete(t) : n.add(t); return n;
                })} />
                <em style={{ borderColor: EDGE_COLORS[t], borderTopStyle: t === "THUOC" ? "dashed" : "solid" }} /> {EDGE_LABEL[t]}
              </label>
            ))}
          </div>
        </div>
        <div className="float-card float-tools">
          <button className="icon-btn" title="Vừa khung" onClick={() => cyRef.current?.fit(undefined, 40)}><Maximize2 size={16} /></button>
          <button className="icon-btn" title="Sắp xếp lại" onClick={() => cyRef.current?.layout({ name: "cose", animate: true, padding: 40, nodeRepulsion: () => 20000, idealEdgeLength: () => 120 }).run()}><RotateCcw size={16} /></button>
          <button className="icon-btn" title="Chỉ giữ node đang xem" onClick={() => expand(focusId, true)}><Trash2 size={16} /></button>
        </div>
      </div>
      <aside className="side-detail">
        {!detail && <div className="skeleton" style={{ height: 160 }} />}
        {detail && (
          <>
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="badge">{CAP_LABEL[nodes[sel]?.cap] || "Đơn vị"}</span>
              <span className="mono muted small">{sel}</span>
            </div>
            <h2 style={{ fontSize: 18, margin: "4px 0 8px", lineHeight: 1.35 }}>{detail.ten}</h2>
            {cur && (
              <>
                <div className="row" style={{ flexWrap: "wrap", gap: 5 }}>
                  <span className="badge ok">Hiệu lực từ {fmtDate(cur.hieu_luc_tu)}</span>
                  {cur.nguon_sua_doi && <span className="badge warn">{VERSION_LABEL[cur.loai_phien_ban]} bởi {cur.nguon_ten}</span>}
                  {detail.versions.length > 1 && <span className="badge">{detail.versions.length} phiên bản</span>}
                </div>
                <p style={{ fontSize: 14, lineHeight: 1.65 }}>{cur.noi_dung}</p>
              </>
            )}
            <div className="row" style={{ flexWrap: "wrap", gap: 6, marginBottom: 16 }}>
              {sel !== focusId && <button className="btn sm" onClick={() => navigate("graph", sel)}><Waypoints size={14} /> Đặt làm tâm</button>}
              <button className="btn sm" onClick={() => expand(sel)}>Mở rộng</button>
              {cur && <button className="btn sm" onClick={() => navigate("history", sel)}><History size={14} /> Lịch sử</button>}
              {cur && <button className="btn sm" onClick={() => navigate("chat", null, { q: `Giải thích quy định tại ${longLabel(sel)}` })}><MessageSquare size={14} /> Hỏi</button>}
            </div>
            <div className="group-title">Liên kết ({neighbors.length})</div>
            <div className="nb-list">
              {neighbors.map((e) => {
                const other = e.source === sel ? e.target : e.source;
                return (
                  <button key={`${e.source}|${e.type}|${e.target}`} className="nb" onClick={() => setSel(other)}>
                    <span className="badge" style={{ color: EDGE_COLORS[e.type] }}>{e.source === sel ? "→" : "←"} {EDGE_LABEL[e.type]}</span>
                    <span className="grow">{shortLabel(other)}</span>
                  </button>
                );
              })}
              {neighbors.length === 0 && <div className="muted small">Bấm “Mở rộng” để tải các liên kết.</div>}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
