// F2 Tra cứu văn bản theo ngày áp dụng: danh sách 12 văn bản, xem toàn văn dạng cây Chương/Điều/Khoản/Điểm. Phụ trách: TV2.
import { useEffect, useMemo, useRef, useState } from "react";
import { FileText, History, MessageSquare, Search, Waypoints } from "lucide-react";
import { api, today } from "../api.js";
import DatePicker from "../components/DatePicker.jsx";
import { fmtDate, fmtNum, longLabel, VERSION_LABEL } from "../lib/format.js";
import { navigate } from "../lib/router.js";
import { scrollIntoContainer } from "../lib/scroll.js";

const ROLE = { goc: ["Văn bản gốc", "accent"], sua_doi: ["Sửa đổi", "warn"], doi_chieu: ["Đối chiếu", ""] };

function UnitRow({ u, date, docId, hit, refMap }) {
  const cls = { Dieu: "lv-dieu", Khoan: "lv-khoan", Diem: "lv-diem" }[u.cap] || "";
  let text = u.noi_dung;
  if (u.cap === "Khoan") text = `${u.so}. ${u.noi_dung}`;
  if (u.cap === "Diem") text = `${u.so}) ${u.noi_dung}`;
  let body = null;   // Điều không chia khoản: tiêu đề Điều + nội dung
  if (u.cap === "Dieu" && !u.noi_dung.startsWith("Điều ")) {
    text = `Điều ${u.so}. ${u.tieu_de || ""}`;
    body = u.noi_dung;
  }
  return (
    <div ref={(el) => { if (el) refMap.current[u.id] = el; }}
      className={`lv ${cls} ${u.nguon_sua_doi ? "amended" : ""} ${hit ? "hit" : ""}`}>
      {text}
      {body && <div style={{ fontWeight: 400, marginTop: 4 }}>{body}</div>}
      {u.nguon_sua_doi && (
        <span className="badge warn lv-tag" title={`Phiên bản do ${longLabel(u.nguon_sua_doi)} tạo ra`}>
          {VERSION_LABEL[u.loai_phien_ban] || "Sửa đổi"} · hiệu lực {fmtDate(u.hieu_luc_tu)}
        </span>
      )}
      {u.cap !== "Chuong" && (
        <span className="lv-actions">
          <button className="icon-btn" title="Hỏi về điều khoản này" onClick={() => navigate("chat", null, { q: `Giải thích quy định tại ${longLabel(u.id)}`, date })}><MessageSquare size={14} /></button>
          <button className="icon-btn" title="Lịch sử sửa đổi" onClick={() => navigate("history", u.id)}><History size={14} /></button>
          <button className="icon-btn" title="Xem trên đồ thị" onClick={() => navigate("graph", u.id)}><Waypoints size={14} /></button>
        </span>
      )}
    </div>
  );
}

export default function DocumentsPage({ docId, query }) {
  const [docs, setDocs] = useState(null);
  const [units, setUnits] = useState(null);
  const [date, setDate] = useState(query.get("date") || today());
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const refMap = useRef({});
  const focus = query.get("unit");
  const current = docs?.find((d) => d.id === docId);

  useEffect(() => { api.documents().then(setDocs).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    if (!docId && docs?.length) navigate("docs", docs[0].id);
  }, [docId, docs]);
  useEffect(() => {
    if (!docId) return;
    setUnits(null);
    api.units(docId, date).then(setUnits).catch((e) => setError(e.message));
  }, [docId, date]);
  useEffect(() => {
    if (focus && units) setTimeout(() => {
      const el = refMap.current[focus];
      scrollIntoContainer(el, el?.closest(".split-right"));
    }, 60);
  }, [focus, units]);

  const shown = useMemo(() => {
    if (!units) return [];
    const f = filter.trim().toLowerCase();
    if (!f) return units;
    return units.filter((u) => u.cap === "Chuong" || u.noi_dung.toLowerCase().includes(f));
  }, [units, filter]);
  const amendedCount = units?.filter((u) => u.nguon_sua_doi).length || 0;

  return (
    <div className="split">
      <div className="split-left">
        <div className="side-section" style={{ padding: "0 4px 10px" }}>Văn bản trong kho</div>
        {!docs && [0, 1, 2, 3, 4].map((i) => <div key={i} className="skeleton" style={{ height: 58, margin: "0 4px 8px" }} />)}
        {docs?.map((d) => (
          <div key={d.id} className={`doc-item ${d.id === docId ? "active" : ""}`} onClick={() => navigate("docs", d.id, { date })}>
            <div className="row">
              <span className="t grow">{d.so_hieu}</span>
              <span className={`badge ${ROLE[d.vai_tro]?.[1] || ""}`}>{ROLE[d.vai_tro]?.[0] || d.vai_tro}</span>
            </div>
            <div className="d">{d.ten}</div>
            <div className="d muted">Hiệu lực {d.hieu_luc_tu ? fmtDate(d.hieu_luc_tu) : "–"} · {fmtNum(d.so_dieu)} điều</div>
          </div>
        ))}
      </div>
      <div className="split-right">
        {error && <div className="banner error" style={{ margin: 20 }}>{error}</div>}
        {current && (
          <>
            <div className="doc-head">
              <div className="row" style={{ marginBottom: 6 }}>
                <span className={`badge ${ROLE[current.vai_tro]?.[1] || ""}`}>{current.loai}</span>
                <span className="muted small">{current.co_quan} · ban hành {fmtDate(current.ngay_ban_hanh)}</span>
                <span className="grow" />
                <DatePicker value={date} onChange={(d) => { setDate(d); navigate("docs", docId, { date: d }); }} label="Xem tại" />
              </div>
              <h2>{current.so_hieu} – {current.ten}</h2>
              <div className="row" style={{ marginTop: 10 }}>
                <div className="search-box grow" style={{ maxWidth: 420 }}>
                  <Search size={15} />
                  <input className="input" placeholder="Lọc trong văn bản…" value={filter} onChange={(e) => setFilter(e.target.value)} />
                </div>
                <span className="muted small">
                  {units ? `${fmtNum(units.filter((u) => u.cap !== "Chuong").length)} đơn vị còn hiệu lực ngày ${fmtDate(date)}` : "Đang tải…"}
                  {amendedCount > 0 && <> · <span style={{ color: "var(--graph)" }}>{amendedCount} đơn vị đã được sửa đổi</span></>}
                </span>
              </div>
            </div>
            <div className="doc-body">
              {!units && [0, 1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="skeleton" style={{ height: 18, margin: "12px 0", width: `${60 + (i * 7) % 40}%` }} />)}
              {units && shown.length === 0 && <div className="empty"><FileText size={28} /><br />Không có đơn vị nào khớp</div>}
              {shown.map((u) => u.cap === "Chuong" ? (
                <div key={u.vid} className="lv-chuong"><small>CHƯƠNG {u.so}</small>{u.tieu_de}</div>
              ) : (
                <UnitRow key={u.vid} u={u} date={date} docId={docId} hit={u.id === focus} refMap={refMap} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
