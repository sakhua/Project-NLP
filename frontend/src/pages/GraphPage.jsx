// F3 Khám phá đồ thị tri thức: tìm một điều khoản, bấm đúp để mở rộng các node lân cận. Phụ trách: TV2.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { History, Maximize2, MessageSquare, RotateCcw, Search, Trash2, Waypoints } from "lucide-react";
import { api } from "../api.js";
import ContextGraph, { EDGE_COLORS, NODE_COLORS } from "../components/ContextGraph.jsx";
import { CAP_LABEL, EDGE_LABEL, fmtDate, longLabel, shortLabel, VERSION_LABEL } from "../lib/format.js";
import { navigate } from "../lib/router.js";
import { readRecent, rememberRecent } from "../lib/recent.js";

const START = "ND168_2024.D6.K9.b";
const EDGE_TYPES = ["THAM_CHIEU", "THUOC", "SUA_DOI", "BO_SUNG", "THAY_THE", "BAI_BO", "HUONG_DAN"];

// Gợi ý khi chưa gõ gì: các điều khoản hay dùng khi demo (đều có nhiều liên kết trên đồ thị)
const SUGGESTED = [
  { id: "ND168_2024.D6.K9.b", d: "Ô tô không chấp hành đèn tín hiệu (vượt đèn đỏ)" },
  { id: "ND168_2024.D6.K16.b", d: "Ô tô bị trừ 04 điểm giấy phép lái xe" },
  { id: "ND168_2024.D6.K11.a", d: "Ô tô có nồng độ cồn vượt quá 80 mg/100 ml máu" },
  { id: "ND168_2024.D6.K3.m", d: "Chở trẻ em dưới 10 tuổi ngồi cùng hàng ghế người lái (đã sửa đổi)" },
  { id: "ND168_2024.D7.K7.c", d: "Xe máy không chấp hành đèn tín hiệu" },
  { id: "TT38_2024.D6.K1", d: "Tốc độ tối đa trong khu vực đông dân cư" },
  { id: "L36_2024.D58.K3", d: "Phục hồi điểm khi giấy phép lái xe bị trừ hết điểm" },
];
function SearchBox({ onPick, current }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [hl, setHl] = useState(0);
  const typing = q.trim().length >= 2;

  useEffect(() => {
    if (!typing) { setRes([]); setLoading(false); return; }
    setLoading(true);
    const t = setTimeout(() => api.search(q.trim(), 12)
      .then((r) => { setRes(r); setHl(0); }).catch(() => setRes([])).finally(() => setLoading(false)), 250);
    return () => clearTimeout(t);
  }, [q, typing]);

  // Danh sách hiển thị: đang gõ → kết quả tìm; chưa gõ → gần đây + gợi ý
  const items = useMemo(() => {
    if (typing) return res.map((r) => ({ id: r.id, t: r.ten, d: r.noi_dung, group: "Kết quả" }));
    const recent = readRecent().filter((id) => id !== current).slice(0, 4)
      .map((id) => ({ id, t: longLabel(id), d: SUGGESTED.find((x) => x.id === id)?.d || shortLabel(id), group: "Xem gần đây" }));
    const seen = new Set(recent.map((x) => x.id));
    const sugg = SUGGESTED.filter((x) => !seen.has(x.id) && x.id !== current)
      .map((x) => ({ id: x.id, t: longLabel(x.id), d: x.d, group: "Gợi ý" }));
    return [...recent, ...sugg];
  }, [typing, res, open, current]); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (it) => { onPick(it.id); setOpen(false); setQ(""); };
  return (
    <div className="float-card" style={{ position: "relative", width: 440, padding: 6 }}>
      <div className="search-box">
        <Search size={15} />
        <input className="input" style={{ border: 0, boxShadow: "none" }} value={q}
          placeholder="Tìm theo mã hoặc nội dung, vd. vượt đèn đỏ"
          onFocus={() => { setOpen(true); setHl(0); }} onBlur={() => setTimeout(() => setOpen(false), 150)}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setHl((h) => Math.min(h + 1, items.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setHl((h) => Math.max(h - 1, 0)); }
            if (e.key === "Enter" && items[hl]) pick(items[hl]);
            if (e.key === "Escape") { setOpen(false); e.currentTarget.blur(); }
          }} />
      </div>
      {open && (
        <div className="float-card results">
          {typing && loading && res.length === 0 && <div className="result-note">Đang tìm…</div>}
          {typing && !loading && res.length === 0 && (
            <div className="result-note">Không tìm thấy điều khoản nào. Thử gõ có dấu, hoặc gõ mã như ND168_2024.D6.K9</div>
          )}
          {items.map((it, i) => (
            <div key={it.id + it.group}>
              {(i === 0 || items[i - 1].group !== it.group) && <div className="result-group">{it.group}</div>}
              <button className={`result ${i === hl ? "hl" : ""}`} onMouseEnter={() => setHl(i)} onMouseDown={() => pick(it)}>
                <div className="t">{it.t}</div>
                <div className="d">{it.d}</div>
              </button>
            </div>
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

  useEffect(() => { expand(focusId, true); setSel(focusId); rememberRecent(focusId); }, [focusId, expand]);
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
          <SearchBox onPick={(id) => navigate("graph", id)} current={focusId} />
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
