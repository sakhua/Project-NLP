// Lịch sử sửa đổi: các điều khoản đã được sửa, bổ sung, thay thế, bãi bỏ; dòng thời gian phiên bản và so sánh thay đổi.
import { useEffect, useMemo, useState } from "react";
import { FileText, GitCompare, History, MessageSquare, Search, Waypoints } from "lucide-react";
import { api, today } from "../api.js";
import { diffWords, docShort, fmtDate, longLabel, VERSION_LABEL } from "../lib/format.js";
import { navigate } from "../lib/router.js";

function Diff({ a, b }) {
  return (
    <div className="tl-text">
      {diffWords(a, b).map((p, i) => (p.type === "same" ? <span key={i}>{p.text}</span>
        : <span key={i} className={p.type === "add" ? "diff-add" : "diff-del"}>{p.text}</span>))}
    </div>
  );
}

function Detail({ uid }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [compare, setCompare] = useState(true);
  useEffect(() => {
    setD(null); setErr("");
    api.unit(uid).then(setD).catch((e) => setErr(e.message));
  }, [uid]);
  if (err) return <div className="banner error">{err}</div>;
  if (!d) return <div className="skeleton" style={{ height: 200 }} />;
  const now = today();
  const versions = d.versions;
  const isCurrent = (v) => v.hieu_luc_tu <= now && (!v.hieu_luc_den || now < v.hieu_luc_den);
  return (
    <>
      <div className="row" style={{ marginBottom: 4 }}>
        <span className="badge">{docShort(d.id.split(".")[0])}</span>
        <span className="mono muted small">{d.id}</span>
      </div>
      <h2 className="page-title" style={{ fontSize: 22 }}>{d.ten}</h2>
      <div className="row" style={{ margin: "10px 0 4px", flexWrap: "wrap" }}>
        <span className="muted small grow">{versions.length} phiên bản · {d.sua_doi_boi.length} lần tác động bởi văn bản sửa đổi</span>
        {versions.length > 1 && (
          <button className={`btn sm ${compare ? "primary" : ""}`} onClick={() => setCompare(!compare)}><GitCompare size={14} /> So sánh thay đổi</button>
        )}
        <button className="btn sm" onClick={() => navigate("docs", d.id.split(".")[0], { unit: d.id })}><FileText size={14} /> Văn bản</button>
        <button className="btn sm" onClick={() => navigate("graph", d.id)}><Waypoints size={14} /> Đồ thị</button>
        <button className="btn sm" onClick={() => navigate("chat", null, { q: `Quy định tại ${longLabel(d.id)} thay đổi thế nào qua các lần sửa đổi?` })}><MessageSquare size={14} /> Hỏi</button>
      </div>
      <div className="timeline">
        {[...versions].reverse().map((v, ri) => {
          const i = versions.length - 1 - ri;
          const prev = versions[i - 1];
          const state = isCurrent(v) ? "current" : v.hieu_luc_tu > now ? "future" : "past";
          return (
            <div key={v.vid} className={`tl-item ${state}`}>
              <div className="tl-dot" />
              <div className="tl-card">
                <div className="row" style={{ flexWrap: "wrap" }}>
                  <span className="tl-range grow">Từ {fmtDate(v.hieu_luc_tu)}{v.hieu_luc_den ? ` đến hết ngày trước ${fmtDate(v.hieu_luc_den)}` : " đến nay"}</span>
                  {state === "current" && <span className="badge ok">Đang có hiệu lực</span>}
                  {state === "future" && <span className="badge accent">Sắp có hiệu lực</span>}
                  {state === "past" && <span className="badge">Đã hết hiệu lực</span>}
                  <span className={`badge ${v.loai_phien_ban === "goc" ? "" : "warn"}`}>{VERSION_LABEL[v.loai_phien_ban] || v.loai_phien_ban}</span>
                </div>
                {v.nguon_ten && <div className="small muted" style={{ marginTop: 4 }}>Do {v.nguon_ten} ({v.nguon_sua_doi})</div>}
                {compare && prev ? <Diff a={prev.noi_dung} b={v.noi_dung} /> : <div className="tl-text">{v.noi_dung}</div>}
              </div>
            </div>
          );
        })}
      </div>
      {versions.length === 1 && versions[0].hieu_luc_den && (
        <div className="banner warn" style={{ marginTop: 6 }}>Điều khoản này đã bị bãi bỏ từ {fmtDate(versions[0].hieu_luc_den)}.</div>
      )}
    </>
  );
}

export default function HistoryPage({ uid }) {
  const [list, setList] = useState(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [by, setBy] = useState("");
  useEffect(() => { api.amended().then(setList).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { if (!uid && list?.length) navigate("history", (list.find((x) => x.id === "ND168_2024.D6.K3.m") || list[0]).id); }, [uid, list]);

  const sources = useMemo(() => {
    const m = {};
    (list || []).forEach((r) => r.van_ban_sua_ten.forEach((t, i) => { m[r.van_ban_sua[i]] = t; }));
    return Object.entries(m).sort();
  }, [list]);
  const shown = useMemo(() => {
    const f = q.trim().toLowerCase();
    return (list || []).filter((r) => (!by || r.van_ban_sua.includes(by))
      && (!f || r.id.toLowerCase().includes(f) || r.ten.toLowerCase().includes(f) || r.noi_dung.toLowerCase().includes(f)));
  }, [list, q, by]);

  return (
    <div className="split">
      <div className="split-left">
        <div className="side-section" style={{ padding: "0 4px 8px" }}><span><History size={12} /> Điều khoản đã sửa đổi {list ? `(${list.length})` : ""}</span></div>
        <div className="search-box"><Search size={15} />
          <input className="input" placeholder="Tìm theo mã hoặc nội dung…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="chips">
          <button className={`chip ${!by ? "on" : ""}`} onClick={() => setBy("")}>Tất cả</button>
          {sources.map(([id, name]) => (
            <button key={id} className={`chip ${by === id ? "on" : ""}`} onClick={() => setBy(by === id ? "" : id)}>{name.replace("Nghị định", "NĐ").replace("Thông tư", "TT")}</button>
          ))}
        </div>
        {err && <div className="banner error">{err}</div>}
        {!list && !err && [0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 50, marginBottom: 8 }} />)}
        {shown.slice(0, 300).map((r) => (
          <div key={r.id} className={`hist-item ${r.id === uid ? "active" : ""}`} onClick={() => navigate("history", r.id)}>
            <div className="row">
              <span className="t grow">{r.ten}</span>
              <span className="badge">{r.so_phien_ban} bản</span>
            </div>
            <div className="d">{r.noi_dung}</div>
          </div>
        ))}
        {list && shown.length === 0 && <div className="empty small">Không có kết quả</div>}
      </div>
      <div className="split-right">
        <div className="page-inner" style={{ maxWidth: 860 }}>
          {uid ? <Detail uid={uid} /> : <div className="empty">Chọn một điều khoản</div>}
        </div>
      </div>
    </div>
  );
}
