// F2 Tra cứu văn bản theo ngày áp dụng. Phụ trách: TV3 (giao diện), TV2 (API).
import { useEffect, useState } from "react";
import { api, today } from "../api.js";

export default function DocumentsPage({ onOpenGraph }) {
  const [docs, setDocs] = useState([]);
  const [docId, setDocId] = useState("");
  const [date, setDate] = useState(today());
  const [units, setUnits] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => { api.documents().then(setDocs).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    if (docId) api.units(docId, date).then(setUnits).catch((e) => setError(e.message));
  }, [docId, date]);

  return (
    <section>
      <div className="card row">
        <label>Văn bản
          <select value={docId} onChange={(e) => setDocId(e.target.value)}>
            <option value="">— chọn văn bản —</option>
            {docs.map((d) => <option key={d.id} value={d.id}>{d.so_hieu} · {d.ten}</option>)}
          </select>
        </label>
        <label>Ngày áp dụng <input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
      </div>
      {error && <div className="banner error">{error}</div>}
      <ul className="units card">
        {units.map((u) => (
          <li key={u.id} className={`lv-${u.cap}`}>
            <button className="link" onClick={() => onOpenGraph(u.id)}>{u.id}</button>
            {u.tieu_de && <b> {u.tieu_de}</b>}
            <p>{u.noi_dung}</p>
          </li>
        ))}
        {docId && units.length === 0 && <li className="muted">Không có điều khoản còn hiệu lực tại ngày này.</li>}
      </ul>
    </section>
  );
}
